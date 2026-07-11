"""Frontier prompt slimming before L6 escalation (issue #34)."""

from __future__ import annotations

import pytest

from daari.cache.exact import ExactCache
from daari.cache.semantic import SemanticCache
from daari.gateway.internal import DaariMeta, InternalRequest, InternalResponse, Message
from daari.gateway.openai import NO_TOOLS_HINT
from daari.observability.metrics import Metrics
from daari.router.frontier import FrontierExecutor
from daari.router.router import OllamaExecutor, Router
from tests.conftest import NoopEmbedder

LOW_CONFIDENCE = "no"  # forces escalation at every local tier


def _router(tmp_path, seen: dict, **kwargs) -> Router:
    def make_local(tier: str) -> OllamaExecutor:
        executor = OllamaExecutor(base_url="http://test", default_model=f"model-{tier.lower()}", tier=tier)

        async def fake_execute(request: InternalRequest, _tier: str = tier) -> InternalResponse:
            return InternalResponse(
                content=LOW_CONFIDENCE,
                model=f"model-{_tier.lower()}",
                daari_meta=DaariMeta(tier=_tier, executor="ollama", provider_id="ollama", latency_ms=1),
            )

        executor.execute = fake_execute  # type: ignore[method-assign]
        return executor

    frontier = FrontierExecutor(
        base_url="http://frontier.test", default_model="gpt-test", api_key="key", provider="openai"
    )

    async def fake_frontier(request: InternalRequest, **_kw) -> InternalResponse:
        seen["messages"] = [message.model_dump() for message in request.messages]
        return InternalResponse(
            content="frontier answer",
            model="gpt-test",
            daari_meta=DaariMeta(tier="L6", executor="frontier", provider_id="openai", latency_ms=9),
        )

    frontier.execute = fake_frontier  # type: ignore[method-assign]

    return Router(
        cache=ExactCache(str(tmp_path / "l0"), enabled=False),
        semantic_cache=SemanticCache(str(tmp_path / "l1"), NoopEmbedder(), enabled=False),
        ollama_l3=make_local("L3"),
        ollama_l4=make_local("L4"),
        ollama_l5=make_local("L5"),
        metrics=Metrics(),
        frontier=frontier,
        frontier_enabled=True,
        **kwargs,
    )


def _request(messages: list[Message]) -> InternalRequest:
    return InternalRequest(messages=messages, model="llama3.2:3b")


@pytest.mark.asyncio
async def test_no_tools_hint_stripped_before_frontier(tmp_path):
    seen: dict = {}
    router = _router(tmp_path, seen)
    request = _request(
        [
            Message(role="system", content=NO_TOOLS_HINT),
            Message(role="system", content="You are a helpful assistant."),
            Message(role="user", content="hard question"),
        ]
    )
    response = await router.route(request)

    assert response.daari_meta.tier == "L6"
    contents = [message["content"] for message in seen["messages"]]
    assert NO_TOOLS_HINT not in contents
    assert "You are a helpful assistant." in contents


@pytest.mark.asyncio
async def test_duplicate_system_prompts_collapsed(tmp_path):
    seen: dict = {}
    router = _router(tmp_path, seen)
    request = _request(
        [
            Message(role="system", content="Same system prompt."),
            Message(role="system", content="Same system prompt."),
            Message(role="user", content="hard question"),
        ]
    )
    await router.route(request)

    system_contents = [m["content"] for m in seen["messages"] if m["role"] == "system"]
    assert system_contents == ["Same system prompt."]


@pytest.mark.asyncio
async def test_history_trimmed_to_frontier_max(tmp_path):
    seen: dict = {}
    router = _router(tmp_path, seen, frontier_max_history=4)
    history = []
    for i in range(20):
        history.append(Message(role="user", content=f"turn {i}"))
        history.append(Message(role="assistant", content=f"reply {i}"))
    history.append(Message(role="user", content="final hard question"))
    await router.route(_request([Message(role="system", content="sys"), *history]))

    non_system = [m for m in seen["messages"] if m["role"] != "system"]
    assert len(non_system) == 4
    assert non_system[-1]["content"] == "final hard question"


@pytest.mark.asyncio
async def test_slim_disabled_passes_everything_through(tmp_path):
    seen: dict = {}
    router = _router(tmp_path, seen, frontier_slim_prompts=False)
    request = _request(
        [
            Message(role="system", content=NO_TOOLS_HINT),
            Message(role="user", content="hard question"),
        ]
    )
    await router.route(request)

    contents = [message["content"] for message in seen["messages"]]
    assert NO_TOOLS_HINT in contents


@pytest.mark.asyncio
async def test_ledger_records_slimmed_prompt_chars(tmp_path):
    from daari.observability.usage import UsageLedger

    seen: dict = {}
    ledger = UsageLedger(tmp_path / "ledger.sqlite3", enabled=True)
    router = _router(tmp_path, seen, frontier_max_history=2, usage_ledger=ledger)
    bulky = [Message(role="user", content="x" * 500) for _ in range(10)]
    bulky.append(Message(role="user", content="short final"))
    await router.route(_request(bulky))

    slimmed_chars = sum(len(m["content"] or "") for m in seen["messages"])
    report = ledger.report(days=1)
    assert report["days"], "expected a ledger row for today"
    l6_stats = report["days"][0]["tiers"]["L6"]
    assert l6_stats["prompt_chars"] == slimmed_chars
    assert slimmed_chars < 5000
