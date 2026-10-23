"""OpenAI service_tier org/project restriction → one degrade retry (#1867)."""

from __future__ import annotations

import json

import httpx
import pytest

from daari.gateway.internal import DaariMeta, InternalRequest, Message
from daari.gateway.sampling import SamplingParams
from daari.observability.metrics import Metrics
from daari.router.frontier import FrontierExecutor, is_openai_service_tier_restriction
from daari.router.retry import RetryPolicy


def _request(*, service_tier: str | None) -> InternalRequest:
    return InternalRequest(
        messages=[Message(role="user", content="hi")],
        model="gpt-4o-mini",
        sampling=SamplingParams(max_tokens=16, service_tier=service_tier),
    )


def _tier_error() -> httpx.Response:
    return httpx.Response(
        400,
        json={
            "error": {
                "message": (
                    "Invalid `service_tier` argument: The requested service "
                    "tier is not allowed for this project."
                ),
                "type": "invalid_request_error",
                "param": "service_tier",
                "code": "invalid_value",
            }
        },
    )


def _ok(*, service_tier: str = "default") -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "id": "chatcmpl-test",
            "service_tier": service_tier,
            "choices": [
                {
                    "message": {"role": "assistant", "content": "ok"},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5},
        },
    )


def _stream_sse(*, service_tier: str = "default") -> bytes:
    delta = {
        "id": "chatcmpl-s",
        "object": "chat.completion.chunk",
        "choices": [{"delta": {"content": "ok"}, "finish_reason": None}],
    }
    usage = {
        "id": "chatcmpl-s",
        "object": "chat.completion.chunk",
        "service_tier": service_tier,
        "choices": [],
        "usage": {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5},
    }
    return (
        f"data: {json.dumps(delta)}\n\n"
        f"data: {json.dumps(usage)}\n\n"
        "data: [DONE]\n\n"
    ).encode()


def test_detects_service_tier_restriction_by_param():
    assert is_openai_service_tier_restriction(_tier_error()) is True


def test_non_tier_400_is_not_restriction():
    other = httpx.Response(
        400,
        json={
            "error": {
                "message": "Invalid `temperature`",
                "type": "invalid_request_error",
                "param": "temperature",
                "code": "invalid_value",
            }
        },
    )
    assert is_openai_service_tier_restriction(other) is False


@pytest.mark.asyncio
async def test_service_tier_400_retries_once_without_tier_and_bills_response():
    tiers: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        tiers.append(body.get("service_tier"))
        if body.get("service_tier") == "priority":
            return _tier_error()
        return _ok(service_tier="default")

    metrics = Metrics()
    executor = FrontierExecutor(
        base_url="https://api.openai.com/v1",
        default_model="gpt-4o-mini",
        api_key="sk-test",
        provider="openai",
        metrics=metrics,
        retry=RetryPolicy(attempts=3, base_delay=0.0, max_delay=0.0, jitter=0.0),
        transport=httpx.MockTransport(handler),
    )
    response = await executor.execute(
        _request(service_tier="priority"),
        escalated_from="L3",
        local_confidence=0.2,
    )
    assert tiers == ["priority", None]
    assert response.daari_meta.service_tier == "default"
    assert "service_tier_degraded" in (response.daari_meta.warning or "")
    assert metrics.soft_warnings.get("service_tier_degraded") == 1


@pytest.mark.asyncio
async def test_non_tier_400_passthrough_no_retry():
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(
            400,
            json={
                "error": {
                    "message": "Invalid `max_tokens`",
                    "type": "invalid_request_error",
                    "param": "max_tokens",
                    "code": "invalid_value",
                }
            },
        )

    executor = FrontierExecutor(
        base_url="https://api.openai.com/v1",
        default_model="gpt-4o-mini",
        api_key="sk-test",
        provider="openai",
        retry=RetryPolicy(attempts=3, base_delay=0.0, max_delay=0.0, jitter=0.0),
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(httpx.HTTPStatusError) as excinfo:
        await executor.execute(
            _request(service_tier="flex"),
            escalated_from="L3",
            local_confidence=0.2,
        )
    assert excinfo.value.response.status_code == 400
    assert calls == 1


@pytest.mark.asyncio
async def test_streamed_service_tier_400_retries_once_without_tier():
    from daari.gateway.cost_headers import WARNING_HEADER, StreamOutcome

    tiers: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        tiers.append(body.get("service_tier"))
        if body.get("service_tier") == "flex":
            return _tier_error()
        return httpx.Response(
            200,
            content=_stream_sse(service_tier="default"),
            headers={"content-type": "text/event-stream"},
        )

    metrics = Metrics()
    executor = FrontierExecutor(
        base_url="https://api.openai.com/v1",
        default_model="gpt-4o-mini",
        api_key="sk-test",
        provider="openai",
        metrics=metrics,
        transport=httpx.MockTransport(handler),
    )
    events = [
        event
        async for event in executor.stream(
            _request(service_tier="flex"),
            escalated_from="L3",
            local_confidence=0.2,
        )
    ]
    assert tiers == ["flex", None]
    assert events == ["ok"]
    assert executor.last_stream_service_tier == "default"
    meta = DaariMeta(tier="L6", executor="frontier")
    outcome = StreamOutcome(tier="L6", cache="miss")
    executor.apply_service_tier_degraded_warning(meta)
    executor.apply_service_tier_degraded_warning(outcome)
    assert meta.warning == "service_tier_degraded"
    assert outcome.headers()[WARNING_HEADER] == "service_tier_degraded"
    assert metrics.soft_warnings.get("service_tier_degraded") == 1
