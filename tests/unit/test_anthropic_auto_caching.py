"""Anthropic top-level auto_caching via cache_control (#2221)."""

from __future__ import annotations

import json

import httpx
import pytest

from daari.config.settings import Settings
from daari.gateway.internal import InternalRequest, Message
from daari.gateway.sampling import SamplingParams
from daari.router.anthropic_messages import to_anthropic_payload
from daari.router.frontier import FrontierExecutor


def test_settings_auto_caching_defaults_off():
    assert Settings().frontier.auto_caching is False


def test_to_anthropic_payload_injects_top_level_when_auto_caching():
    req = InternalRequest(
        messages=[
            Message(role="system", content="Stable system."),
            Message(role="user", content="hi"),
        ],
        model="daari",
    )
    payload = to_anthropic_payload(
        req, model="claude-sonnet-5-5", prompt_cache=True, auto_caching=True
    )
    assert payload["cache_control"] == {"type": "ephemeral"}
    # Block-level prompt_cache marking still applies.
    assert payload["system"][-1]["cache_control"]["type"] == "ephemeral"


def test_to_anthropic_payload_omits_top_level_when_auto_caching_off():
    req = InternalRequest(
        messages=[Message(role="user", content="hi")],
        model="daari",
    )
    payload = to_anthropic_payload(
        req, model="claude-sonnet-5-5", prompt_cache=False, auto_caching=False
    )
    assert "cache_control" not in payload


def test_client_top_level_cache_control_wins_over_dial():
    req = InternalRequest(
        messages=[Message(role="user", content="hi")],
        model="daari",
        sampling=SamplingParams(cache_control={"type": "ephemeral", "ttl": "1h"}),
    )
    payload = to_anthropic_payload(
        req, model="claude-sonnet-5-5", prompt_cache=False, auto_caching=True
    )
    assert payload["cache_control"] == {"type": "ephemeral", "ttl": "1h"}


def test_from_openai_and_anthropic_bodies_parse_top_level_cache_control():
    openai = SamplingParams.from_openai_body(
        {"cache_control": {"type": "ephemeral", "ttl": "5m"}}
    )
    assert openai.cache_control == {"type": "ephemeral", "ttl": "5m"}
    anthropic = SamplingParams.from_anthropic_body(
        {"cache_control": {"type": "ephemeral"}}
    )
    assert anthropic.cache_control == {"type": "ephemeral"}
    responses = SamplingParams.from_responses_body(
        {"cache_control": {"type": "ephemeral", "ttl": "1h"}}
    )
    assert responses.cache_control == {"type": "ephemeral", "ttl": "1h"}


@pytest.mark.asyncio
async def test_frontier_executor_auto_caching_reaches_anthropic_body():
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        return httpx.Response(
            200, json={"content": [{"type": "text", "text": "ok"}], "stop_reason": "end_turn"}
        )

    executor = FrontierExecutor(
        base_url="https://api.anthropic.com/v1",
        default_model="claude-sonnet-5-5",
        api_key="k",
        provider="anthropic",
        prompt_cache=False,
        auto_caching=True,
        transport=httpx.MockTransport(handler),
    )
    await executor.execute(
        InternalRequest(
            messages=[Message(role="user", content="hello")],
            model="daari",
        ),
        escalated_from="L3",
        local_confidence=0.4,
    )
    assert captured["cache_control"] == {"type": "ephemeral"}


@pytest.mark.asyncio
async def test_openai_executor_does_not_leak_top_level_cache_control():
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        return httpx.Response(
            200, json={"choices": [{"message": {"content": "hi"}}]}
        )

    executor = FrontierExecutor(
        base_url="https://api.openai.com/v1",
        default_model="gpt-4o-mini",
        api_key="k",
        provider="openai",
        auto_caching=True,
        transport=httpx.MockTransport(handler),
    )
    await executor.execute(
        InternalRequest(
            messages=[
                Message(role="system", content="Stable."),
                Message(role="user", content="hello"),
            ],
            model="daari",
            sampling=SamplingParams(cache_control={"type": "ephemeral"}),
        ),
        escalated_from="L3",
        local_confidence=0.4,
    )
    assert "cache_control" not in captured
