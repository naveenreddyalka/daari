"""Warn when a client sets speed and the serving L6 slot is not Anthropic (#1772)."""

from __future__ import annotations

import json

import httpx
import pytest

from daari.gateway.internal import InternalRequest, Message
from daari.gateway.sampling import SamplingParams
from daari.router.frontier import FrontierExecutor


def _request(*, speed: str | None, gate_warning: str | None = None) -> InternalRequest:
    return InternalRequest(
        messages=[Message(role="user", content="hi")],
        model="daari",
        sampling=SamplingParams(max_tokens=16, speed=speed, gate_warning=gate_warning),
    )


def _openai_ok() -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "choices": [{"message": {"role": "assistant", "content": "ok"}}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1},
        },
    )


def _anthropic_ok() -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "content": [{"type": "text", "text": "ok"}],
            "usage": {"input_tokens": 1, "output_tokens": 1, "speed": "fast"},
        },
    )


@pytest.mark.asyncio
async def test_non_anthropic_slot_warns_and_logs_requested_speed(monkeypatch):
    events: list[tuple[str, dict]] = []
    monkeypatch.setattr(
        "daari.gateway.request_log.log_gateway_event",
        lambda event, payload: events.append((event, dict(payload))),
    )
    captured: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(json.loads(request.content))
        return _openai_ok()

    executor = FrontierExecutor(
        base_url="https://api.openai.com/v1",
        default_model="gpt-4o",
        api_key="sk-test",
        provider="openai",
        transport=httpx.MockTransport(handler),
    )
    response = await executor.execute(
        _request(speed="fast"), escalated_from="L3", local_confidence=0.2
    )
    assert "speed" not in captured[0]
    assert response.daari_meta.warning == "speed_ignored"
    logged = [payload for event, payload in events if event == "speed_ignored"]
    assert logged == [{"speed": "fast", "provider": "openai"}]


@pytest.mark.asyncio
async def test_budget_warning_is_kept_and_speed_ignored_event_still_emits(monkeypatch):
    events: list[tuple[str, dict]] = []
    monkeypatch.setattr(
        "daari.gateway.request_log.log_gateway_event",
        lambda event, payload: events.append((event, dict(payload))),
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return _openai_ok()

    executor = FrontierExecutor(
        base_url="https://openrouter.ai/api/v1",
        default_model="gpt-4o",
        api_key="sk-test",
        provider="openrouter",
        transport=httpx.MockTransport(handler),
    )
    response = await executor.execute(
        _request(speed="standard", gate_warning="budget_warning"),
        escalated_from="L3",
        local_confidence=0.2,
    )
    assert response.daari_meta.warning == "budget_warning"
    logged = [payload for event, payload in events if event == "speed_ignored"]
    assert logged == [{"speed": "standard", "provider": "openrouter"}]


@pytest.mark.asyncio
async def test_anthropic_slot_forwards_speed_without_warning(monkeypatch):
    events: list[tuple[str, dict]] = []
    monkeypatch.setattr(
        "daari.gateway.request_log.log_gateway_event",
        lambda event, payload: events.append((event, dict(payload))),
    )
    captured: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(json.loads(request.content))
        return _anthropic_ok()

    executor = FrontierExecutor(
        base_url="https://api.anthropic.com",
        default_model="claude-opus-5-5",
        api_key="sk-ant",
        provider="anthropic",
        transport=httpx.MockTransport(handler),
    )
    response = await executor.execute(
        _request(speed="fast"), escalated_from="L3", local_confidence=0.2
    )
    assert captured[0]["speed"] == "fast"
    assert response.daari_meta.warning != "speed_ignored"
    assert [event for event, _payload in events if event == "speed_ignored"] == []
