"""Anthropic cache_control TTL passthrough + 1h write rates (#434)."""

from __future__ import annotations

import pytest

from daari.config.settings import ModelPrice, PricingSettings
from daari.gateway.internal import InternalRequest, Message
from daari.pricing import cost_usd, resolve_price
from daari.router.anthropic_messages import (
    openai_tools_to_anthropic,
    request_cache_ttl,
    to_anthropic_payload,
)


def _request(**kwargs) -> InternalRequest:
    messages = kwargs.pop("messages", [Message(role="user", content="hello")])
    return InternalRequest(messages=messages, model="daari", **kwargs)


def test_cache_control_ttl_1h_preserved_on_system_block():
    payload = to_anthropic_payload(
        _request(
            messages=[
                Message(
                    role="system",
                    content="long catalog",
                    cache_control={"type": "ephemeral", "ttl": "1h"},
                ),
                Message(role="user", content="q"),
            ]
        ),
        model="claude-sonnet-5",
        prompt_cache=True,
    )
    system = payload["system"]
    assert system[-1]["cache_control"] == {"type": "ephemeral", "ttl": "1h"}


def test_prompt_cache_default_remains_5m_ephemeral_without_ttl():
    payload = to_anthropic_payload(
        _request(
            messages=[
                Message(role="system", content="stable"),
                Message(role="user", content="q"),
            ]
        ),
        model="claude-sonnet-5",
        prompt_cache=True,
    )
    assert payload["system"][-1]["cache_control"] == {"type": "ephemeral"}


def test_tool_cache_control_ttl_preserved():
    tools = [
        {
            "type": "function",
            "function": {
                "name": "search",
                "description": "find things",
                "parameters": {"type": "object", "properties": {}},
            },
            "cache_control": {"type": "ephemeral", "ttl": "1h"},
        }
    ]
    converted = openai_tools_to_anthropic(tools)
    assert converted[0]["cache_control"] == {"type": "ephemeral", "ttl": "1h"}

    payload = to_anthropic_payload(
        _request(
            messages=[Message(role="user", content="go")],
            tools=tools,
        ),
        model="claude-sonnet-5",
    )
    assert payload["tools"][0]["cache_control"]["ttl"] == "1h"


def test_request_cache_ttl_prefers_1h():
    req = _request(
        messages=[
            Message(role="system", content="a", cache_control={"type": "ephemeral"}),
            Message(
                role="system",
                content="b",
                cache_control={"type": "ephemeral", "ttl": "1h"},
            ),
            Message(role="user", content="q"),
        ]
    )
    assert request_cache_ttl(req) == "1h"
    assert request_cache_ttl(_request()) is None


def test_cost_usd_1h_write_uses_distinct_rate():
    pricing = PricingSettings(
        models={
            "claude-sonnet-5": ModelPrice(
                input_per_1m=2.0,
                output_per_1m=10.0,
                cached_input_per_1m=0.20,
                cache_write_1h_per_1m=4.0,
            )
        }
    )
    # 1M write tokens at 1h → $4; no other tokens
    one_h = cost_usd(
        "claude-sonnet-5",
        0,
        0,
        pricing,
        fallback_per_1k=0.002,
        cache_write_tokens=1_000_000,
        cache_ttl="1h",
    )
    assert one_h == pytest.approx(4.0)

    # Missing TTL keeps today's rate (bill writes at input)
    missing = cost_usd(
        "claude-sonnet-5",
        0,
        0,
        pricing,
        fallback_per_1k=0.002,
        cache_write_tokens=1_000_000,
        cache_ttl=None,
    )
    assert missing == pytest.approx(2.0)

    five_m = cost_usd(
        "claude-sonnet-5",
        0,
        0,
        pricing,
        fallback_per_1k=0.002,
        cache_write_tokens=1_000_000,
        cache_ttl="5m",
    )
    assert five_m == pytest.approx(2.0)


def test_default_anthropic_models_have_1h_write_rate():
    pricing = PricingSettings()
    price = resolve_price("claude-sonnet-5", pricing, fallback_per_1k=0.002)
    assert price.cache_write_1h_per_1m == pytest.approx(4.0)  # 2× input
    fable = resolve_price("claude-fable-5-1", pricing, fallback_per_1k=0.002)
    assert fable.cache_write_1h_per_1m == pytest.approx(20.0)
