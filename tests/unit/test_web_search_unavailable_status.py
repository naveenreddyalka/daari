"""Pin WebSearchUnavailable → HTTP status mapping (#1307)."""

from __future__ import annotations

import json

import pytest

from daari.gateway.openai import _web_search_unavailable_response
from daari.gateway.sampling import WebSearchUnavailable


@pytest.mark.parametrize(
    "reason,expected_status",
    [
        ("no_frontier", 403),
        ("frontier_disabled", 501),
        ("frontier_budget_exceeded", 402),
        ("tier_cap:L3", 403),
    ],
)
def test_web_search_unavailable_status_mapping(reason: str, expected_status: int):
    resp = _web_search_unavailable_response(WebSearchUnavailable(reason))
    assert resp.status_code == expected_status
    body = json.loads(resp.body.decode())
    assert body["error"]["type"] == "web_search_unavailable"
    assert body["error"]["code"] == reason
    assert "web_search" in body["error"]["message"].lower()
