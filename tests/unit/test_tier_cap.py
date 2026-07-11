"""Tier cap: routing.max_tier_for_chat + X-Daari-Tier-Cap header (issue #3)."""

from __future__ import annotations

import pytest

from daari.cache.exact import ExactCache
from daari.cache.semantic import SemanticCache
from daari.gateway.internal import DaariMeta, InternalRequest, InternalResponse, Message
from daari.observability.metrics import Metrics
from daari.router.router import OllamaExecutor, Router
from tests.conftest import NoopEmbedder

LONG_PROMPT = "please explain this " + "word " * 300  # >250 words -> L4 without a cap


def _request(text: str = LONG_PROMPT, *, tier_cap: str | None = None, tier_override: str | None = None) -> InternalRequest:
    request = InternalRequest(messages=[Message(role="user", content=text)], model="llama3.2:3b")
    request.meta.tier_cap = tier_cap
    request.meta.tier_override = tier_override
    return request


def _router(tmp_path, *, max_tier_for_chat: str | None = None, calls: list[str] | None = None, content: str = "A confident answer with plenty of length to avoid escalation.") -> Router:
    calls = calls if calls is not None else []

    def make_executor(tier: str) -> OllamaExecutor:
        executor = OllamaExecutor(base_url="http://test", default_model=f"model-{tier.lower()}", tier=tier)

        async def fake_execute(request: InternalRequest, _tier: str = tier) -> InternalResponse:
            calls.append(_tier)
            return InternalResponse(
                content=content,
                model=f"model-{_tier.lower()}",
                daari_meta=DaariMeta(tier=_tier, executor="ollama", provider_id="ollama", latency_ms=1),
            )

        executor.execute = fake_execute  # type: ignore[method-assign]
        return executor

    return Router(
        cache=ExactCache(str(tmp_path / "l0"), enabled=True),
        semantic_cache=SemanticCache(path=str(tmp_path / "l1"), embedder=NoopEmbedder(), enabled=False),
        ollama_l3=make_executor("L3"),
        ollama_l4=make_executor("L4"),
        ollama_l5=make_executor("L5"),
        metrics=Metrics(),
        max_tier_for_chat=max_tier_for_chat,
    )


@pytest.mark.asyncio
async def test_no_cap_long_prompt_goes_l4(tmp_path):
    router = _router(tmp_path)
    response = await router.route(_request())
    assert response.daari_meta.tier == "L4"


@pytest.mark.asyncio
async def test_config_cap_clamps_to_l3(tmp_path):
    router = _router(tmp_path, max_tier_for_chat="L3")
    response = await router.route(_request())
    assert response.daari_meta.tier == "L3"


@pytest.mark.asyncio
async def test_header_cap_clamps_to_l3(tmp_path):
    router = _router(tmp_path)
    response = await router.route(_request(tier_cap="L3"))
    assert response.daari_meta.tier == "L3"


@pytest.mark.asyncio
async def test_header_cap_wins_over_config(tmp_path):
    router = _router(tmp_path, max_tier_for_chat="L3")
    response = await router.route(_request(tier_cap="L4"))
    assert response.daari_meta.tier == "L4"


@pytest.mark.asyncio
async def test_tier_override_beats_cap(tmp_path):
    router = _router(tmp_path, max_tier_for_chat="L3")
    response = await router.route(_request(tier_override="L5"))
    assert response.daari_meta.tier == "L5"


@pytest.mark.asyncio
async def test_escalation_respects_cap(tmp_path):
    calls: list[str] = []
    # "no" forces low confidence at every tier; without a cap this walks L3->L4->L5.
    router = _router(tmp_path, max_tier_for_chat="L3", calls=calls, content="no")
    response = await router.route(_request("hello there"))
    assert calls == ["L3"], "cap must stop local escalation above L3"
    assert response.daari_meta.warning == "below_confidence_threshold"


def test_stream_tier_chain_is_capped(tmp_path):
    router = _router(tmp_path, max_tier_for_chat="L3")
    assert router._stream_tier_chain(_request()) == ["L3"]


def test_invalid_cap_ignored(tmp_path):
    router = _router(tmp_path, max_tier_for_chat="L9")
    assert router._stream_tier_chain(_request()) == ["L4", "L3"]
