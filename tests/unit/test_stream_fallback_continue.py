"""Opt-in mid-stream fallback continuation after upstream death (#2003)."""

from __future__ import annotations

import json

import pytest

from daari.cache.exact import ExactCache
from daari.cache.semantic import SemanticCache
from daari.gateway.internal import (
    DaariMeta,
    InternalRequest,
    InternalResponse,
    Message,
    RequestMeta,
)
from daari.observability.metrics import Metrics
from daari.router.circuit_breaker import CircuitBreaker
from daari.router.router import OllamaExecutor, Router
from tests.conftest import NoopEmbedder


def _req(
    text: str = "explain quantum decoherence",
    *,
    no_frontier: bool = False,
    tier: str = "L4",
) -> InternalRequest:
    return InternalRequest(
        messages=[Message(role="user", content=text)],
        model="daari",
        meta=RequestMeta(no_frontier=no_frontier, tier_override=tier),
    )


class _DyingL4(OllamaExecutor):
    async def execute(self, request, model=None, **kwargs):  # type: ignore[override]
        return InternalResponse(
            content="partial",
            model=self.default_model,
            daari_meta=DaariMeta(tier="L4", executor="ollama", provider_id="ollama"),
        )

    async def stream(self, request, **kwargs):  # type: ignore[override]
        yield {"message": {"content": "PARTIAL "}}
        raise RuntimeError("L4 died mid-stream")


class _HealthyL3(OllamaExecutor):
    def __init__(self) -> None:
        super().__init__(base_url="http://l3", default_model="llama3.2:3b")
        self.seen_messages: list[list[Message]] = []

    async def execute(self, request, model=None, **kwargs):  # type: ignore[override]
        return InternalResponse(
            content="ok",
            model=self.default_model,
            daari_meta=DaariMeta(tier="L3", executor="ollama", provider_id="ollama"),
        )

    async def stream(self, request, **kwargs):  # type: ignore[override]
        self.seen_messages.append(list(request.messages))
        yield {"message": {"content": "CONTINUED"}}
        yield {"done": True}


class _DyingL3(OllamaExecutor):
    async def execute(self, request, model=None, **kwargs):  # type: ignore[override]
        return InternalResponse(
            content="x",
            model=self.default_model,
            daari_meta=DaariMeta(tier="L3", executor="ollama", provider_id="ollama"),
        )

    async def stream(self, request, **kwargs):  # type: ignore[override]
        yield {"message": {"content": "only "}}
        raise RuntimeError("L3 died mid-stream")


class _FrontierContinue:
    def __init__(self) -> None:
        self.stream_calls = 0
        self.breaker = CircuitBreaker(failure_threshold=1, cooldown_seconds=60.0)

    async def execute(self, request, escalated_from=None, local_confidence=None):
        raise AssertionError("buffered escalate must not run")

    async def stream(self, request, escalated_from=None, local_confidence=None):
        self.stream_calls += 1
        yield "L6-CONTINUE"


def _router(tmp_path, *, l4, l3, stream_fallback_continue: bool = False, **kwargs) -> Router:
    return Router(
        cache=ExactCache(str(tmp_path / "l0"), enabled=False),
        semantic_cache=SemanticCache(str(tmp_path / "l1"), NoopEmbedder(), enabled=False),
        ollama=l3,
        ollama_l3=l3,
        ollama_l4=l4,
        ollama_l5=l4,
        metrics=Metrics(),
        stream_fallback_continue=stream_fallback_continue,
        **kwargs,
    )


async def _collect(agen) -> str:
    return "".join([chunk async for chunk in agen])


def _openai_text(body: str) -> str:
    out = []
    for line in body.splitlines():
        if not line.startswith("data: ") or line.endswith("[DONE]"):
            continue
        payload = json.loads(line[len("data: ") :])
        if "error" in payload:
            continue
        for choice in payload.get("choices", []):
            out.append(choice.get("delta", {}).get("content") or "")
    return "".join(out)


def _openai_errors(body: str) -> list[dict]:
    out = []
    for line in body.splitlines():
        if not line.startswith("data: ") or line.endswith("[DONE]"):
            continue
        payload = json.loads(line[len("data: ") :])
        if "error" in payload:
            out.append(payload)
    return out


def _chunk_ids(body: str) -> set[str]:
    ids: set[str] = set()
    for line in body.splitlines():
        if not line.startswith("data: ") or line.endswith("[DONE]"):
            continue
        payload = json.loads(line[len("data: ") :])
        if isinstance(payload, dict) and payload.get("id"):
            ids.add(payload["id"])
    return ids


@pytest.fixture
def captured_events(monkeypatch):
    events: list[tuple[str, dict]] = []

    def capture(event: str, payload: dict) -> None:
        events.append((event, payload))

    monkeypatch.setattr("daari.gateway.request_log.log_gateway_event", capture)
    return events


@pytest.mark.asyncio
async def test_stream_fallback_continue_replays_partial_on_next_tier(
    tmp_path, captured_events
):
    l4 = _DyingL4(base_url="http://l4", default_model="qwen2.5:14b")
    l3 = _HealthyL3()
    router = _router(tmp_path, l4=l4, l3=l3, stream_fallback_continue=True)
    body = await _collect(router.stream_openai_chunks(_req()))
    text = _openai_text(body)
    assert "PARTIAL " in text
    assert "CONTINUED" in text
    assert not _openai_errors(body)
    assert len(_chunk_ids(body)) == 1
    assert l3.seen_messages, "fallback hop must see rewritten transcript"
    assert any(
        m.role == "assistant" and "PARTIAL" in (m.content or "") for m in l3.seen_messages[0]
    )
    assert router.metrics.stream_fallback_continue >= 1
    assert "stream_fallback_continue" in [name for name, _ in captured_events]


@pytest.mark.asyncio
async def test_stream_fallback_continue_off_keeps_incomplete_on_last_tier(
    tmp_path, captured_events
):
    dying = _DyingL3(base_url="http://l3", default_model="llama3.2:3b")
    router = _router(tmp_path, l4=dying, l3=dying, stream_fallback_continue=False)
    body = await _collect(router.stream_openai_chunks(_req(tier="L3")))
    assert "only " in _openai_text(body)
    errors = _openai_errors(body)
    assert errors and errors[-1]["error"]["type"] == "stream_incomplete"
    assert router.metrics.stream_fallback_continue == 0


@pytest.mark.asyncio
async def test_stream_fallback_continue_respects_no_frontier(tmp_path, captured_events):
    dying = _DyingL3(base_url="http://l3", default_model="llama3.2:3b")
    frontier = _FrontierContinue()
    router = _router(
        tmp_path,
        l4=dying,
        l3=dying,
        stream_fallback_continue=True,
        frontier=frontier,
        frontier_enabled=True,
    )
    body = await _collect(router.stream_openai_chunks(_req("say hello", no_frontier=True, tier="L3")))
    assert frontier.stream_calls == 0
    errors = _openai_errors(body)
    assert errors and errors[-1]["error"]["type"] == "stream_incomplete"
    assert "L6-CONTINUE" not in _openai_text(body)
