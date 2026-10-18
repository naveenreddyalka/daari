"""Frontier web-search calls bill $0.01 on top of token cost (#1770)."""

from __future__ import annotations

import pytest

from daari.gateway.provider_prefs import web_search_fee_usd
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


def _with_fee(data: dict) -> float:
    fee = web_search_fee_usd(data)
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


def test_two_search_calls_add_two_cents():
    data = {
        "output": [
            {"type": "web_search_call", "action": {"type": "search"}},
            {"type": "web_search_call"},
        ]
    }
    assert web_search_fee_usd(data) == pytest.approx(0.02)
    assert _with_fee(data) == pytest.approx(_token_cost() + 0.02)


def test_three_web_search_requests_add_three_cents():
    data = {"usage": {"server_tool_use": {"web_search_requests": 3}}}
    assert web_search_fee_usd(data) == pytest.approx(0.03)
    assert _with_fee(data) == pytest.approx(_token_cost() + 0.03)


def test_both_shapes_bill_the_larger_count():
    data = {
        "output": [
            {"type": "web_search_call", "action": {"type": "search"}},
            {"type": "web_search_call", "action": {"type": "search"}},
        ],
        "usage": {"server_tool_use": {"web_search_requests": 3}},
    }
    assert web_search_fee_usd(data) == pytest.approx(0.03)
    assert _with_fee(data) == pytest.approx(_token_cost() + 0.03)


def test_open_page_and_token_only_add_nothing():
    open_page = {
        "output": [
            {"type": "web_search_call", "action": {"type": "open_page"}},
            {"type": "web_search_call", "action": {"type": "find_in_page"}},
        ]
    }
    assert web_search_fee_usd(open_page) == 0.0
    assert _with_fee(open_page) == pytest.approx(_token_cost())
    assert web_search_fee_usd({"output": [{"type": "message"}]}) == 0.0
    assert _with_fee({}) == pytest.approx(_token_cost())
