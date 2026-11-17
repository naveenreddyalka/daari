"""Honest Anthropic stop_reason ↔ OpenAI finish_reason mapping (#2232)."""

from __future__ import annotations

import json

import httpx
import pytest

from daari.gateway.internal import InternalRequest, Message
from daari.router.anthropic_messages import (
    anthropic_stop_to_finish_reason,
    finish_reason_to_anthropic_stop,
)
from daari.router.frontier import FrontierExecutor


@pytest.mark.parametrize(
    ("anthropic", "openai"),
    [
        ("end_turn", "stop"),
        ("max_tokens", "length"),
        ("tool_use", "tool_calls"),
        ("pause_turn", "pause_turn"),
        ("refusal", "refusal"),
        (None, "stop"),
        ("", "stop"),
    ],
)
def test_anthropic_stop_to_finish_reason(anthropic: str | None, openai: str) -> None:
    assert anthropic_stop_to_finish_reason(anthropic) == openai


@pytest.mark.parametrize(
    ("openai", "anthropic"),
    [
        ("stop", "end_turn"),
        ("length", "max_tokens"),
        ("tool_calls", "tool_use"),
        ("pause_turn", "pause_turn"),
        ("refusal", "refusal"),
        (None, "end_turn"),
        ("", "end_turn"),
    ],
)
def test_finish_reason_to_anthropic_stop(openai: str | None, anthropic: str) -> None:
    assert finish_reason_to_anthropic_stop(openai) == anthropic


def _anthropic_request() -> InternalRequest:
    return InternalRequest(
        messages=[Message(role="user", content="hi")],
        model="daari",
        temperature=0.0,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("upstream_stop", "expected_finish"),
    [
        ("end_turn", "stop"),
        ("max_tokens", "length"),
        ("tool_use", "tool_calls"),
        ("pause_turn", "pause_turn"),
        ("refusal", "refusal"),
    ],
)
async def test_frontier_anthropic_records_stop_reason(
    upstream_stop: str, expected_finish: str
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "content": [{"type": "text", "text": "partial"}],
                "stop_reason": upstream_stop,
                "usage": {"input_tokens": 2, "output_tokens": 1},
            },
        )

    executor = FrontierExecutor(
        base_url="https://api.anthropic.com",
        default_model="claude-sonnet-4-0",
        api_key="sk-ant-test",
        provider="anthropic",
        transport=httpx.MockTransport(handler),
    )
    response = await executor.execute(
        _anthropic_request(), escalated_from="L3", local_confidence=0.2
    )
    assert response.finish_reason == expected_finish
