"""Per-tool server-side fees beyond web search (#2197)."""

from __future__ import annotations

import pytest

from daari.config.settings import PricingSettings
from daari.gateway.provider_prefs import (
    server_tool_fees,
    web_search_fee_usd,
)
from daari.observability.spend import compute_request_usd


def _token_cost() -> float:
    spent, _avoided = compute_request_usd(
        tier="L6",
        model="gpt-4o-mini",
        input_tokens=1000,
        output_tokens=100,
        cached_tokens=0,
        pricing=None,
        fallback_per_1k=0.002,
    )
    return spent


def _with_tool_cost(data: dict, *, pricing: PricingSettings | None = None) -> float:
    fee, _usage = server_tool_fees(data, pricing=pricing)
    spent, _avoided = compute_request_usd(
        tier="L6",
        model="gpt-4o-mini",
        input_tokens=1000,
        output_tokens=100,
        cached_tokens=0,
        pricing=None,
        fallback_per_1k=0.002,
        tool_cost_usd=fee,
    )
    return spent


def test_file_search_call_bills_default_fee():
    data = {"output": [{"type": "file_search_call"}, {"type": "file_search_call"}]}
    fee, usage = server_tool_fees(data)
    assert usage == {"file_search": 2}
    assert fee == pytest.approx(0.005)
    assert _with_tool_cost(data) == pytest.approx(_token_cost() + 0.005)


def test_web_fetch_and_code_execution_shapes():
    data = {
        "output": [
            {"type": "web_fetch_call"},
            {"type": "code_interpreter_call"},
        ],
        "usage": {
            "server_tool_use": {
                "web_fetch_requests": 2,
                "code_execution_requests": 3,
            }
        },
    }
    fee, usage = server_tool_fees(data)
    # web_fetch / code_execution: max(items, anthropic requests); defaults $0.
    assert usage == {"web_fetch": 2, "code_execution": 3}
    assert fee == pytest.approx(0.0)


def test_mixed_tools_sum_and_web_search_max_not_sum():
    data = {
        "output": [
            {"type": "web_search_call", "action": {"type": "search"}},
            {"type": "web_search_call"},
            {"type": "file_search_call"},
            {"type": "web_search_call", "action": {"type": "open_page"}},
        ],
        "usage": {"server_tool_use": {"web_search_requests": 3}},
    }
    fee, usage = server_tool_fees(data)
    assert usage == {"web_search": 3, "file_search": 1}
    assert fee == pytest.approx(0.03 + 0.0025)
    assert _with_tool_cost(data) == pytest.approx(_token_cost() + 0.0325)


def test_config_override_wins_and_unknown_tools_bill_zero():
    pricing = PricingSettings(server_tools={"web_search": 0.05, "file_search": 0.01})
    data = {
        "output": [
            {"type": "web_search_call"},
            {"type": "file_search_call"},
            {"type": "computer_call"},
        ]
    }
    fee, usage = server_tool_fees(data, pricing=pricing)
    assert usage == {"web_search": 1, "file_search": 1}
    assert fee == pytest.approx(0.06)
    # Override replaces defaults for named keys; missing keys still resolve defaults.
    fee_fetch, usage_fetch = server_tool_fees(
        {"output": [{"type": "web_fetch_call"}]},
        pricing=pricing,
    )
    assert usage_fetch == {"web_fetch": 1}
    assert fee_fetch == pytest.approx(0.0)


def test_web_search_fee_usd_still_works_for_legacy_callers():
    data = {
        "output": [
            {"type": "web_search_call", "action": {"type": "search"}},
            {"type": "file_search_call"},
        ]
    }
    # Legacy helper remains web-search-only so old single-float callers stay stable.
    assert web_search_fee_usd(data) == pytest.approx(0.01)
    total, usage = server_tool_fees(data)
    assert usage == {"web_search": 1, "file_search": 1}
    assert total == pytest.approx(0.0125)


def test_tool_cost_outside_service_tier_multiplier():
    """Tool fees stay outside token multipliers (compute_request_usd path)."""
    data = {"output": [{"type": "web_search_call"}, {"type": "file_search_call"}]}
    fee, _usage = server_tool_fees(data)
    spent_std, _ = compute_request_usd(
        tier="L6",
        model="gpt-4o-mini",
        input_tokens=1000,
        output_tokens=100,
        cached_tokens=0,
        pricing=None,
        fallback_per_1k=0.002,
        service_tier="standard",
        tool_cost_usd=fee,
    )
    spent_fast, _ = compute_request_usd(
        tier="L6",
        model="gpt-4o-mini",
        input_tokens=1000,
        output_tokens=100,
        cached_tokens=0,
        pricing=None,
        fallback_per_1k=0.002,
        service_tier="fast",
        tool_cost_usd=fee,
    )
    token_std, _ = compute_request_usd(
        tier="L6",
        model="gpt-4o-mini",
        input_tokens=1000,
        output_tokens=100,
        cached_tokens=0,
        pricing=None,
        fallback_per_1k=0.002,
        service_tier="standard",
    )
    token_fast, _ = compute_request_usd(
        tier="L6",
        model="gpt-4o-mini",
        input_tokens=1000,
        output_tokens=100,
        cached_tokens=0,
        pricing=None,
        fallback_per_1k=0.002,
        service_tier="fast",
    )
    assert spent_std == pytest.approx(token_std + fee)
    assert spent_fast == pytest.approx(token_fast + fee)
    assert (spent_fast - token_fast) == pytest.approx(fee)
    assert (spent_std - token_std) == pytest.approx(fee)
