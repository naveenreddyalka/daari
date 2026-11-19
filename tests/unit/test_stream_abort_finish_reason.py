"""Abort / missing finish_reason must fail visibly (#2241)."""

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
from daari.router.stream_terminal import (
    StreamTerminalError,
    is_abort_finish_reason,
    stream_ended_without_terminal,
)
from tests.conftest import NoopEmbedder


def _request(text: str = "say hello") -> InternalRequest:
    return InternalRequest(messages=[Message(role="user", content=text)], model="daari")


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


def _finish_reasons(body: str) -> list[str]:
    found = []
    for line in body.splitlines():
        if not line.startswith("data: ") or line.endswith("[DONE]"):
            continue
        payload = json.loads(line[len("data: ") :])
        for choice in payload.get("choices") or []:
            fr = choice.get("finish_reason")
            if fr:
                found.append(fr)
    return found


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("abort", True),
        ("ABORT", True),
        ("stop", False),
        ("tool_calls", False),
        ("length", False),
        (None, False),
        ("", False),
    ],
)
def test_is_abort_finish_reason(raw: str | None, expected: bool) -> None:
    assert is_abort_finish_reason(raw) is expected


def test_stream_ended_without_terminal_requires_output() -> None:
    assert stream_ended_without_terminal(had_output=True, saw_terminal=False) is True
    assert stream_ended_without_terminal(had_output=True, saw_terminal=True) is False
    assert stream_ended_without_terminal(had_output=False, saw_terminal=False) is False


@pytest.fixture
def captured_events(monkeypatch):
    events: list[tuple[str, dict]] = []

    def capture(event: str, payload: dict) -> None:
        events.append((event, payload))

    monkeypatch.setattr("daari.gateway.request_log.log_gateway_event", capture)
    return events


class _AbortLocal(OllamaExecutor):
    async def execute(self, request, model=None, **kwargs):  # type: ignore[override]
        return InternalResponse(
            content="partial",
            model=self.default_model,
            daari_meta=DaariMeta(tier="L3", executor="ollama", provider_id="ollama"),
        )

    async def stream(self, request, **kwargs):  # type: ignore[override]
        yield {"message": {"content": "partial abort "}}
        yield {"done": True, "done_reason": "abort"}


class _MissingTerminalLocal(OllamaExecutor):
    async def execute(self, request, model=None, **kwargs):  # type: ignore[override]
        return InternalResponse(
            content="partial",
            model=self.default_model,
            daari_meta=DaariMeta(tier="L3", executor="ollama", provider_id="ollama"),
        )

    async def stream(self, request, **kwargs):  # type: ignore[override]
        yield {"message": {"content": "truncated without done"}}
        # Iterator ends — no done / finish_reason.


class _CleanStopLocal(OllamaExecutor):
    async def execute(self, request, model=None, **kwargs):  # type: ignore[override]
        return InternalResponse(
            content="ok",
            model=self.default_model,
            daari_meta=DaariMeta(tier="L3", executor="ollama", provider_id="ollama"),
        )

    async def stream(self, request, **kwargs):  # type: ignore[override]
        yield {"message": {"content": "all good"}}
        yield {"done": True, "done_reason": "stop"}


def _pool(breaker: CircuitBreaker) -> LocalBackendPool:
    return LocalBackendPool(
        slots=[
            LocalBackendSlot(
                id="host-a",
                base_url="http://host-a",
                model="llama3.2:3b",
                breaker=breaker,
            )
        ]
    )


@pytest.mark.asyncio
async def test_abort_finish_reason_emits_stream_incomplete(tmp_path, captured_events):
    breaker = CircuitBreaker(failure_threshold=1, cooldown_seconds=60.0)
    executor = _AbortLocal(base_url="http://test", default_model="llama3.2:3b")
    router = _router(tmp_path, executor, local_pool=_pool(breaker))
    body = await _collect(router.stream_openai_chunks(_request()))
    assert "partial abort" in body
    errors = _openai_errors(body)
    assert errors and errors[-1]["error"]["type"] == "stream_incomplete"
    assert "stop" not in _finish_reasons(body)
    assert breaker.failures >= 1
    assert "stream_incomplete" in [name for name, _ in captured_events]


@pytest.mark.asyncio
async def test_missing_finish_reason_emits_stream_incomplete(tmp_path, captured_events):
    breaker = CircuitBreaker(failure_threshold=1, cooldown_seconds=60.0)
    executor = _MissingTerminalLocal(base_url="http://test", default_model="llama3.2:3b")
    router = _router(tmp_path, executor, local_pool=_pool(breaker))
    body = await _collect(router.stream_openai_chunks(_request()))
    assert "truncated without done" in body
    errors = _openai_errors(body)
    assert errors and errors[-1]["error"]["type"] == "stream_incomplete"
    assert "stop" not in _finish_reasons(body)
    assert breaker.failures >= 1
    assert "stream_incomplete" in [name for name, _ in captured_events]


@pytest.mark.asyncio
async def test_clean_stop_stream_unchanged(tmp_path):
    breaker = CircuitBreaker(failure_threshold=1, cooldown_seconds=60.0)
    executor = _CleanStopLocal(base_url="http://test", default_model="llama3.2:3b")
    router = _router(tmp_path, executor, local_pool=_pool(breaker))
    body = await _collect(router.stream_openai_chunks(_request()))
    assert "all good" in body
    assert not _openai_errors(body)
    assert "stop" in _finish_reasons(body)
    assert breaker.failures == 0


@pytest.mark.asyncio
async def test_openai_executor_abort_raises_stream_terminal_error():
    from daari.router.openai_executor import OpenAICompatExecutor

    lines = [
        'data: {"choices":[{"delta":{"content":"hi"},"finish_reason":null}]}',
        'data: {"choices":[{"delta":{},"finish_reason":"abort"}]}',
        "data: [DONE]",
    ]

    async def fake_aiter_lines():
        for line in lines:
            yield line

    class _Resp:
        status_code = 200

        def aiter_lines(self):
            return fake_aiter_lines()

        async def aread(self):
            return b""

    class _CM:
        async def __aenter__(self):
            return _Resp()

        async def __aexit__(self, *args):
            return False

    class _Client:
        def stream(self, *args, **kwargs):
            return _CM()

    executor = OpenAICompatExecutor(
        base_url="http://openai.test",
        default_model="gpt-test",
        tier="L3",
    )
    executor._http = _Client()  # type: ignore[attr-defined]

    with pytest.raises(StreamTerminalError) as excinfo:
        async for _ in executor.stream(_request()):
            pass
    assert "abort" in str(excinfo.value).lower()


@pytest.mark.asyncio
async def test_openai_executor_missing_finish_reason_raises():
    from daari.router.openai_executor import OpenAICompatExecutor

    lines = [
        'data: {"choices":[{"delta":{"content":"hi"},"finish_reason":null}]}',
        "data: [DONE]",
    ]

    async def fake_aiter_lines():
        for line in lines:
            yield line

    class _Resp:
        status_code = 200

        def aiter_lines(self):
            return fake_aiter_lines()

        async def aread(self):
            return b""

    class _CM:
        async def __aenter__(self):
            return _Resp()

        async def __aexit__(self, *args):
            return False

    class _Client:
        def stream(self, *args, **kwargs):
            return _CM()

    executor = OpenAICompatExecutor(
        base_url="http://openai.test",
        default_model="gpt-test",
        tier="L3",
    )
    executor._http = _Client()  # type: ignore[attr-defined]

    with pytest.raises(StreamTerminalError) as excinfo:
        async for _ in executor.stream(_request()):
            pass
    assert "missing" in str(excinfo.value).lower() or "finish_reason" in str(excinfo.value).lower()
