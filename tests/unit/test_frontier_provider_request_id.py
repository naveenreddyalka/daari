"""Frontier HTTP failures record the upstream provider request id (#1771)."""

from __future__ import annotations

import httpx
import pytest

from daari.gateway.internal import InternalRequest, Message
from daari.router.frontier import FrontierExecutor
from daari.router.retry import RetryPolicy, provider_request_id

FAST = RetryPolicy(attempts=2, base_delay=0.0, max_delay=0.0, jitter=0.0)


def _request() -> InternalRequest:
    return InternalRequest(model="daari", messages=[Message(role="user", content="hi")])


def _ok_body() -> dict:
    return {
        "choices": [{"message": {"role": "assistant", "content": "ok"}}],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1},
    }


def test_provider_request_id_prefers_request_id_then_fallbacks():
    assert provider_request_id({"x-request-id": "x", "request-id": "req_1"}) == "req_1"
    assert provider_request_id({"X-Request-Id": "x-only"}) == "x-only"
    assert provider_request_id({"anthropic-request-id": "ant_1"}) == "ant_1"
    assert provider_request_id({"request-id": "  ", "x-request-id": "x2"}) == "x2"
    assert provider_request_id({}) is None
    assert provider_request_id(None) is None


@pytest.mark.asyncio
async def test_frontier_http_failure_records_request_id(monkeypatch):
    events: list[tuple[str, dict]] = []
    monkeypatch.setattr(
        "daari.gateway.request_log.log_gateway_event",
        lambda event, payload: events.append((event, dict(payload))),
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"error": "slow"}, headers={"request-id": "req_abc"})

    executor = FrontierExecutor(
        base_url="http://frontier.test",
        default_model="gpt-4o",
        api_key="sk-test",
        transport=httpx.MockTransport(handler),
        retry=RetryPolicy(attempts=1),
    )
    with pytest.raises(httpx.HTTPStatusError):
        await executor.execute(_request(), escalated_from="L5", local_confidence=0.1)

    failed = [payload for event, payload in events if event == "frontier_http_error"]
    assert len(failed) == 1
    assert failed[0]["provider_request_id"] == "req_abc"
    assert failed[0]["status"] == 429


@pytest.mark.asyncio
async def test_frontier_http_failure_omits_id_when_headers_absent(monkeypatch):
    events: list[tuple[str, dict]] = []
    monkeypatch.setattr(
        "daari.gateway.request_log.log_gateway_event",
        lambda event, payload: events.append((event, dict(payload))),
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": "bad"})

    executor = FrontierExecutor(
        base_url="http://frontier.test",
        default_model="gpt-4o",
        api_key="sk-test",
        transport=httpx.MockTransport(handler),
        retry=RetryPolicy(attempts=1),
    )
    with pytest.raises(httpx.HTTPStatusError):
        await executor.execute(_request(), escalated_from="L5", local_confidence=0.1)

    failed = [payload for event, payload in events if event == "frontier_http_error"]
    assert len(failed) == 1
    assert "provider_request_id" not in failed[0]


@pytest.mark.asyncio
async def test_frontier_stream_failure_records_anthropic_request_id(monkeypatch):
    events: list[tuple[str, dict]] = []
    monkeypatch.setattr(
        "daari.gateway.request_log.log_gateway_event",
        lambda event, payload: events.append((event, dict(payload))),
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, headers={"anthropic-request-id": "ant_stream"})

    executor = FrontierExecutor(
        base_url="https://api.anthropic.com",
        default_model="claude",
        api_key="sk-ant",
        provider="anthropic",
        transport=httpx.MockTransport(handler),
        retry=RetryPolicy(attempts=1),
    )
    with pytest.raises(httpx.HTTPStatusError):
        async for _event in executor.stream(
            _request(), escalated_from="L5", local_confidence=0.1
        ):
            pass

    failed = [payload for event, payload in events if event == "frontier_http_error"]
    assert failed and failed[0]["provider_request_id"] == "ant_stream"


@pytest.mark.asyncio
async def test_frontier_success_does_not_log_http_error(monkeypatch):
    events: list[tuple[str, dict]] = []
    monkeypatch.setattr(
        "daari.gateway.request_log.log_gateway_event",
        lambda event, payload: events.append((event, dict(payload))),
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_ok_body(), headers={"request-id": "req_ok"})

    executor = FrontierExecutor(
        base_url="http://frontier.test",
        default_model="gpt-4o",
        api_key="sk-test",
        transport=httpx.MockTransport(handler),
        retry=FAST,
    )
    response = await executor.execute(_request(), escalated_from="L5", local_confidence=0.1)
    assert response.content == "ok"
    assert [event for event, _payload in events if event == "frontier_http_error"] == []


@pytest.mark.asyncio
async def test_retry_trace_step_includes_provider_request_id(monkeypatch):
    from daari.observability.trace import end_trace, start_trace

    events: list[tuple[str, dict]] = []
    monkeypatch.setattr(
        "daari.gateway.request_log.log_gateway_event",
        lambda event, payload: events.append((event, dict(payload))),
    )
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(503, json={"error": "busy"}, headers={"request-id": "req_retry"})
        return httpx.Response(200, json=_ok_body())

    executor = FrontierExecutor(
        base_url="http://frontier.test",
        default_model="gpt-4o",
        api_key="sk-test",
        transport=httpx.MockTransport(handler),
        retry=FAST,
    )
    trace = start_trace()
    try:
        await executor.execute(_request(), escalated_from="L5", local_confidence=0.1)
    finally:
        end_trace()

    retries = [step for step in trace.steps if step.get("step") == "upstream_retry"]
    assert len(retries) == 1
    assert retries[0]["detail"]["provider_request_id"] == "req_retry"
    assert retries[0]["detail"]["status"] == 503
