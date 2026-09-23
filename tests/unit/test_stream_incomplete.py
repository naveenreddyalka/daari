"""In-band stream_incomplete + breaker feedback on truncated streams (#973)."""

from __future__ import annotations

import json

import pytest

from daari.cache.exact import ExactCache
from daari.cache.semantic import SemanticCache
from daari.gateway.internal import DaariMeta, InternalRequest, InternalResponse, Message
from daari.observability.metrics import Metrics
from daari.router.circuit_breaker import CircuitBreaker
from daari.router.local_pool import LocalBackendPool, LocalBackendSlot
from daari.router.router import OllamaExecutor, Router
from tests.conftest import NoopEmbedder


def _request(text: str = "explain quantum decoherence") -> InternalRequest:
    return InternalRequest(messages=[Message(role="user", content=text)], model="daari")


class _PartialLocal(OllamaExecutor):
    """Dies after the first delta so the client has already seen partial text."""

    async def execute(self, request, model=None, **kwargs):  # type: ignore[override]
        return InternalResponse(
            content="idk",
            model=self.default_model,
            daari_meta=DaariMeta(tier="L3", executor="ollama", provider_id="ollama"),
        )

    async def stream(self, request, **kwargs):  # type: ignore[override]
        yield {"message": {"content": "partial local "}}
        raise RuntimeError("local host died mid-stream")


def _dying_local() -> _PartialLocal:
    return _PartialLocal(base_url="http://test", default_model="llama3.2:3b")


class _DyingFrontier:
    def __init__(self, *, breaker: CircuitBreaker | None = None) -> None:
        self.api_key = "sk-test"
        self.breaker = breaker or CircuitBreaker(failure_threshold=1, cooldown_seconds=60.0)
        self.stream_calls = 0

    async def execute(self, request, escalated_from=None, local_confidence=None):
        raise AssertionError("buffered escalate must not run in relay tests")

    async def stream(self, request, escalated_from=None, local_confidence=None):
        self.stream_calls += 1
        yield "FRONTIER "
        yield "PARTIAL"
        raise RuntimeError("frontier died mid-relay")


def _router(tmp_path, executor, **kwargs) -> Router:
    return Router(
        cache=ExactCache(str(tmp_path / "l0"), enabled=True),
        semantic_cache=SemanticCache(str(tmp_path / "l1"), NoopEmbedder(), enabled=True),
        ollama=executor,
        ollama_l3=executor,
        ollama_l4=executor,
        ollama_l5=executor,
        metrics=Metrics(),
        **kwargs,
    )


async def _collect(agen) -> str:
    return "".join([chunk async for chunk in agen])


def _openai_errors(body: str) -> list[dict]:
    out = []
    for line in body.splitlines():
        if not line.startswith("data: ") or line.endswith("[DONE]"):
            continue
        payload = json.loads(line[len("data: ") :])
        if "error" in payload:
            out.append(payload)
    return out


def _anthropic_errors(body: str) -> list[dict]:
    out = []
    for line in body.splitlines():
        if not line.startswith("data: "):
            continue
        payload = json.loads(line[len("data: ") :])
        if payload.get("type") == "error" or "error" in payload:
            out.append(payload)
    return out


@pytest.fixture
def captured_events(monkeypatch):
    events: list[tuple[str, dict]] = []

    def capture(event: str, payload: dict) -> None:
        events.append((event, payload))

    monkeypatch.setattr("daari.gateway.request_log.log_gateway_event", capture)
    return events


@pytest.mark.asyncio
async def test_frontier_mid_relay_emits_stream_incomplete_and_records_breaker(
    tmp_path, captured_events
):
    breaker = CircuitBreaker(failure_threshold=1, cooldown_seconds=60.0)
    frontier = _DyingFrontier(breaker=breaker)
    executor = _dying_local()

    async def low_conf_stream(request, **kwargs):
        yield {"message": {"content": "idk"}}
        yield {"done": True}

    executor.stream = low_conf_stream  # type: ignore[method-assign]
    router = _router(
        tmp_path,
        executor,
        frontier=frontier,
        frontier_enabled=True,
        confidence_threshold=0.99,
    )
    body = await _collect(router.stream_openai_chunks(_request()))
    assert frontier.stream_calls == 1
    assert '"content": "FRONTIER "' in body or "FRONTIER " in body
    assert '"content": "PARTIAL"' in body or "PARTIAL" in body
    errors = _openai_errors(body)
    assert errors, "truncated relay must emit an in-band error"
    err = errors[-1]["error"]
    assert isinstance(err, dict)
    assert err["type"] == "stream_incomplete"
    assert body.rstrip().endswith("data: [DONE]")
    assert breaker.failures >= 1
    assert breaker.state == "open"
    assert "stream_incomplete" in [name for name, _ in captured_events]


@pytest.mark.asyncio
async def test_local_mid_stream_emits_stream_incomplete_and_trips_slot_breaker(
    tmp_path, captured_events
):
    breaker = CircuitBreaker(failure_threshold=1, cooldown_seconds=60.0)
    slot = LocalBackendSlot(
        id="dying-host",
        base_url="http://dying",
        model="llama3.2:3b",
        breaker=breaker,
    )
    pool = LocalBackendPool(slots=[slot])
    executor = _dying_local()
    router = _router(tmp_path, executor, local_pool=pool)
    body = await _collect(router.stream_openai_chunks(_request("say hello")))
    assert "partial local" in body
    errors = _openai_errors(body)
    assert errors and errors[-1]["error"]["type"] == "stream_incomplete"
    assert body.rstrip().endswith("data: [DONE]")
    assert breaker.failures >= 1
    assert breaker.state == "open"
    assert "stream_incomplete" in [name for name, _ in captured_events]


@pytest.mark.asyncio
async def test_anthropic_mid_stream_emits_stream_incomplete(tmp_path, captured_events):
    breaker = CircuitBreaker(failure_threshold=1, cooldown_seconds=60.0)
    slot = LocalBackendSlot(
        id="dying-host",
        base_url="http://dying",
        model="llama3.2:3b",
        breaker=breaker,
    )
    pool = LocalBackendPool(slots=[slot])
    executor = _dying_local()
    router = _router(tmp_path, executor, local_pool=pool)
    body = await _collect(router.stream_anthropic_events(_request("say hello")))
    assert "partial local" in body
    errors = _anthropic_errors(body)
    assert errors, "Anthropic truncated stream must emit an error event"
    err = errors[-1].get("error") or {}
    assert err.get("type") == "stream_incomplete"
    assert breaker.failures >= 1
    assert "stream_incomplete" in [name for name, _ in captured_events]


@pytest.mark.asyncio
async def test_partial_stream_never_written_to_cache(tmp_path):
    breaker = CircuitBreaker(failure_threshold=3, cooldown_seconds=60.0)
    slot = LocalBackendSlot(
        id="dying-host",
        base_url="http://dying",
        model="llama3.2:3b",
        breaker=breaker,
    )
    pool = LocalBackendPool(slots=[slot])
    executor = _dying_local()
    router = _router(tmp_path, executor, local_pool=pool)
    request = _request("cache me please with enough text")
    await _collect(router.stream_openai_chunks(request))
    assert router.cache.get(request) is None
    nearest, _sim = await router.semantic_cache.nearest(request)
    assert nearest is None
