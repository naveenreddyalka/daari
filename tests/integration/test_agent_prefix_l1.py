"""G1b: agent prefix L1 — hit on stable prefix, miss when the last tool result changes."""

from __future__ import annotations

import pytest

from daari.cache.exact import ExactCache
from daari.cache.semantic import SemanticCache, agent_prefix_text, agent_suffix_hash
from daari.gateway.internal import DaariMeta, InternalRequest, InternalResponse, Message
from daari.observability.metrics import Metrics
from daari.router.router import OllamaExecutor, Router

TOOLS = [{"type": "function", "function": {"name": "lookup_deal"}}]


class PrefixEmbedder:
    """Deterministic embeddings: identical text is identical, other text is orthogonal."""

    def __init__(self) -> None:
        self.vectors: dict[str, list[float]] = {}
        self._next = 0

    async def embed(self, text: str) -> list[float] | None:
        if text not in self.vectors:
            vector = [0.0] * 16
            vector[self._next % 16] = 1.0
            self._next += 1
            self.vectors[text] = vector
        return list(self.vectors[text])


def _request(tool_result: str, *, call_id: str = "c1") -> InternalRequest:
    messages = [
        Message(role="system", content="You are a deal assistant."),
        Message(role="user", content="Summarize the Stripe deal."),
        Message(
            role="assistant",
            content=None,
            tool_calls=[
                {"id": call_id, "type": "function", "function": {"name": "lookup_deal"}}
            ],
        ),
        Message(role="tool", content=tool_result, tool_call_id=call_id),
    ]
    return InternalRequest(messages=messages, model="llama3.2:3b", tools=TOOLS)


def _router(tmp_path) -> tuple[Router, Metrics, list[int]]:
    calls = [0]

    async def fake_execute(request: InternalRequest) -> InternalResponse:
        calls[0] += 1
        last_tool = next(
            (m.content for m in reversed(request.messages) if m.role == "tool"), "none"
        )
        return InternalResponse(
            content=f"answer for {last_tool}",
            model="llama3.2:3b",
            daari_meta=DaariMeta(
                tier="L3", executor="ollama", provider_id="ollama", latency_ms=1
            ),
        )

    ollama = OllamaExecutor(base_url="http://test", default_model="llama3.2:3b")
    ollama.execute = fake_execute  # type: ignore[method-assign]
    metrics = Metrics()
    router = Router(
        cache=ExactCache(str(tmp_path / "l0"), enabled=True),
        semantic_cache=SemanticCache(
            str(tmp_path / "l1"),
            PrefixEmbedder(),
            enabled=True,
            similarity_threshold=0.9,
        ),
        ollama=ollama,
        metrics=metrics,
    )
    return router, metrics, calls


def test_agent_prefix_text_excludes_last_tool_result():
    request = _request("balance: 100")
    text = agent_prefix_text(request)
    assert "balance: 100" not in text
    assert "Summarize the Stripe deal." in text
    assert agent_prefix_text(_request("balance: 999")) == text
    assert agent_suffix_hash(_request("balance: 999")) != agent_suffix_hash(request)


@pytest.mark.asyncio
async def test_changed_last_tool_result_does_not_serve_old_answer(tmp_path):
    router, metrics, calls = _router(tmp_path)

    first = await router.route(_request("balance: 100"))
    second = await router.route(_request("balance: 999"))

    assert first.content == "answer for balance: 100"
    assert second.content == "answer for balance: 999"
    assert second.daari_meta.cache_hit is False
    assert "L1" not in metrics.tiers


@pytest.mark.asyncio
async def test_identical_prefix_and_tool_result_hits_prefix_l1(tmp_path):
    router, metrics, calls = _router(tmp_path)

    await router.route(_request("balance: 100"))
    # Same stable prefix and same tool result; a fresh tool_call id changes the
    # exact L0 key, so only prefix-L1 can serve this.
    second = await router.route(_request("balance: 100", call_id="c2"))

    assert second.daari_meta.tier == "L1"
    assert second.daari_meta.cache_hit is True
    assert second.content == "answer for balance: 100"
    assert metrics.tiers["L1"].cache_hits == 1


@pytest.mark.asyncio
async def test_identical_agent_turn_still_hits_l0(tmp_path):
    router, metrics, calls = _router(tmp_path)

    await router.route(_request("balance: 100"))
    before = calls[0]
    second = await router.route(_request("balance: 100"))

    assert second.daari_meta.tier == "L0"
    assert calls[0] == before
