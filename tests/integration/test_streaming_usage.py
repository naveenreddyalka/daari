"""Streaming usage accounting (#320).

Every streamed request must hit the usage ledger exactly once with the
provider-reported token counts, regardless of how the backend surfaces usage:
a final usage-only chunk, running totals on every chunk, or nothing at all.
Covers the OpenAI SSE path, the Anthropic /v1/messages path and the Ollama
NDJSON facade, plus client cancellation mid-stream.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

from daari.gateway.internal import InternalRequest, Message
from daari.router.router import AppContext
from daari.server.app import create_app

PROMPT_TOKENS = 11
COMPLETION_TOKENS = 7
DELTAS = ["The answer ", "is four, ", "as expected."]


@pytest.fixture
def app(settings):
    application = create_app(settings)
    application.state.ctx = AppContext.from_settings(settings)
    return application


class RecordingLedger:
    """Wraps the real ledger so tests can count `record` calls and still
    read the persisted rows back through `report()` / `by_client()`."""

    def __init__(self, inner: Any) -> None:
        self._inner = inner
        self.calls: list[dict[str, Any]] = []

    @property
    def enabled(self) -> bool:
        return bool(self._inner.enabled)

    def record(self, **kwargs: Any) -> None:
        self.calls.append(kwargs)
        self._inner.record(**kwargs)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)


def _install_ledger(app) -> RecordingLedger:
    router = app.state.ctx.router
    assert router.usage_ledger is not None and router.usage_ledger.enabled
    ledger = RecordingLedger(router.usage_ledger)
    router.usage_ledger = ledger
    return ledger


def _final_usage_events() -> list[dict[str, Any]]:
    """Ollama / vLLM shape: content deltas, then one terminal event carrying
    the only usage report."""
    events: list[dict[str, Any]] = [
        {"message": {"role": "assistant", "content": delta}, "done": False} for delta in DELTAS
    ]
    events.append(
        {
            "message": {"role": "assistant", "content": ""},
            "done": True,
            "prompt_eval_count": PROMPT_TOKENS,
            "eval_count": COMPLETION_TOKENS,
        }
    )
    return events


def _running_total_events() -> list[dict[str, Any]]:
    """Providers that attach cumulative usage to every chunk. Summing these
    would report 1+2+...+n; only the last value is the truth."""
    events: list[dict[str, Any]] = []
    running = 0
    step = COMPLETION_TOKENS // len(DELTAS)
    for delta in DELTAS:
        running += step
        events.append(
            {
                "message": {"role": "assistant", "content": delta},
                "done": False,
                "prompt_eval_count": PROMPT_TOKENS,
                "eval_count": running,
            }
        )
    events.append(
        {
            "message": {"role": "assistant", "content": ""},
            "done": True,
            "prompt_eval_count": PROMPT_TOKENS,
            "eval_count": COMPLETION_TOKENS,
        }
    )
    return events


def _mock_stream(monkeypatch, app, events: list[dict[str, Any]]) -> None:
    class FakeStreamExecutor:
        default_model = "llama3.2:3b"

        async def stream(self, request: InternalRequest):
            for event in events:
                yield event

    monkeypatch.setattr(
        app.state.ctx.router, "_executor_for_tier", lambda tier: FakeStreamExecutor()
    )


def _sse_payloads(body: str) -> list[dict[str, Any]]:
    payloads = []
    for line in body.splitlines():
        if line.startswith("data:") and "[DONE]" not in line:
            payloads.append(json.loads(line[len("data:") :].strip()))
    return payloads


def _assert_single_reported_record(ledger: RecordingLedger, *, tier: str = "L3") -> None:
    assert len(ledger.calls) == 1, ledger.calls
    call = ledger.calls[0]
    assert call["tier"] == tier
    assert call["input_tokens"] == PROMPT_TOKENS
    assert call["output_tokens"] == COMPLETION_TOKENS
    totals = ledger.report(days=1)["totals"]
    assert totals["requests"] == 1
    assert totals["local_requests"] == 1


@pytest.mark.asyncio
async def test_openai_stream_final_usage_chunk_recorded_once(app, monkeypatch):
    ledger = _install_ledger(app)
    _mock_stream(monkeypatch, app, _final_usage_events())

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/chat/completions",
            json={
                "model": "daari",
                "stream": True,
                "messages": [{"role": "user", "content": "what is two plus two"}],
            },
        )

    assert response.status_code == 200
    _assert_single_reported_record(ledger)
    usage_chunks = [p for p in _sse_payloads(response.text) if p.get("usage")]
    assert len(usage_chunks) == 1
    assert usage_chunks[0]["usage"] == {
        "prompt_tokens": PROMPT_TOKENS,
        "completion_tokens": COMPLETION_TOKENS,
        "total_tokens": PROMPT_TOKENS + COMPLETION_TOKENS,
    }


@pytest.mark.asyncio
async def test_openai_stream_running_totals_are_not_summed(app, monkeypatch):
    ledger = _install_ledger(app)
    _mock_stream(monkeypatch, app, _running_total_events())

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/chat/completions",
            json={
                "model": "daari",
                "stream": True,
                "messages": [{"role": "user", "content": "what is two plus two"}],
            },
        )

    assert response.status_code == 200
    _assert_single_reported_record(ledger)


@pytest.mark.asyncio
async def test_anthropic_stream_records_usage_once(app, monkeypatch):
    ledger = _install_ledger(app)
    _mock_stream(monkeypatch, app, _final_usage_events())

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/messages",
            json={
                "model": "daari",
                "max_tokens": 64,
                "stream": True,
                "messages": [{"role": "user", "content": "what is two plus two"}],
            },
        )

    assert response.status_code == 200
    _assert_single_reported_record(ledger)
    events = _sse_payloads(response.text)
    starts = [e for e in events if e.get("type") == "message_start"]
    deltas = [e for e in events if e.get("type") == "message_delta"]
    assert len(starts) == 1 and len(deltas) == 1
    assert starts[0]["message"]["usage"]["input_tokens"] == PROMPT_TOKENS
    # message_delta.usage is cumulative per the Anthropic contract: the one
    # delta we emit carries the final total, not a per-chunk increment.
    assert deltas[0]["usage"]["output_tokens"] == COMPLETION_TOKENS


@pytest.mark.asyncio
async def test_anthropic_stream_running_totals_are_not_summed(app, monkeypatch):
    ledger = _install_ledger(app)
    _mock_stream(monkeypatch, app, _running_total_events())

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/messages",
            json={
                "model": "daari",
                "max_tokens": 64,
                "stream": True,
                "messages": [{"role": "user", "content": "what is two plus two"}],
            },
        )

    assert response.status_code == 200
    _assert_single_reported_record(ledger)


@pytest.mark.asyncio
async def test_ollama_facade_stream_records_once_and_reports_counts(app, monkeypatch):
    ledger = _install_ledger(app)
    _mock_stream(monkeypatch, app, _final_usage_events())

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/chat",
            json={
                "model": "daari",
                "stream": True,
                "messages": [{"role": "user", "content": "what is two plus two"}],
            },
        )

    assert response.status_code == 200
    _assert_single_reported_record(ledger)
    lines = [json.loads(line) for line in response.text.strip().splitlines()]
    finals = [line for line in lines if line.get("done")]
    assert len(finals) == 1
    assert finals[0]["prompt_eval_count"] == PROMPT_TOKENS
    assert finals[0]["eval_count"] == COMPLETION_TOKENS


@pytest.mark.asyncio
async def test_stream_without_reported_usage_records_estimate_once(app, monkeypatch):
    ledger = _install_ledger(app)
    events = [
        {"message": {"role": "assistant", "content": delta}, "done": False} for delta in DELTAS
    ]
    events.append({"message": {"role": "assistant", "content": ""}, "done": True})
    _mock_stream(monkeypatch, app, events)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/chat/completions",
            json={
                "model": "daari",
                "stream": True,
                "messages": [{"role": "user", "content": "what is two plus two"}],
            },
        )

    assert response.status_code == 200
    assert len(ledger.calls) == 1
    call = ledger.calls[0]
    completion_chars = sum(len(d) for d in DELTAS)
    assert call["completion_chars"] == completion_chars
    assert call["output_tokens"] == completion_chars // 4


@pytest.mark.asyncio
async def test_client_cancel_mid_stream_never_double_counts(app, monkeypatch):
    ledger = _install_ledger(app)
    _mock_stream(monkeypatch, app, _final_usage_events())
    router = app.state.ctx.router
    request = InternalRequest(
        model="daari",
        stream=True,
        messages=[Message(role="user", content="what is two plus two")],
    )

    stream = router.stream_openai_chunks(request)
    await stream.__anext__()
    await stream.__anext__()
    await stream.aclose()

    # Cancellation records at most the usage seen so far; never a second row.
    assert len(ledger.calls) <= 1
    for call in ledger.calls:
        assert call["output_tokens"] <= COMPLETION_TOKENS

    cancelled_rows = len(ledger.calls)
    async for _ in router.stream_openai_chunks(request):
        pass
    assert len(ledger.calls) == cancelled_rows + 1
    assert ledger.calls[-1]["output_tokens"] == COMPLETION_TOKENS


@pytest.mark.asyncio
async def test_stream_usage_feeds_budget_and_savings_once(app, monkeypatch):
    """Budget spend and the savings report read the same ledger rows, so one
    streamed request must show up as exactly one request for its client."""
    ledger = _install_ledger(app)
    _mock_stream(monkeypatch, app, _final_usage_events())

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/chat/completions",
            headers={"X-Daari-Client-Id": "finops-client"},
            json={
                "model": "daari",
                "stream": True,
                "messages": [{"role": "user", "content": "what is two plus two"}],
            },
        )

    assert response.status_code == 200
    _assert_single_reported_record(ledger)
    by_client = ledger.by_client(days=1)
    row = next(entry for entry in by_client if entry["client_id"] == "finops-client")
    assert row["requests"] == 1
    assert row["local_requests"] == 1
    assert row["frontier_requests"] == 0
