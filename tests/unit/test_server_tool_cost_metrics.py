"""Prometheus / stats counters for server-side tool fee spend (#2288)."""

from __future__ import annotations

import pytest

from daari.gateway.internal import DaariMeta, InternalRequest, InternalResponse, Message
from daari.gateway.provider_prefs import resolve_server_tool_prices, server_tool_fees
from daari.observability.metrics import Metrics
from daari.observability.prometheus import render_prometheus
from daari.router.router import AppContext


def test_prometheus_emits_server_tool_cost_series_when_recorded():
    metrics = Metrics()
    text0 = render_prometheus(metrics)
    assert "# HELP daari_server_tool_cost_usd_total" in text0
    assert "# TYPE daari_server_tool_cost_usd_total counter" in text0
    # No tool labels until a non-zero fee is recorded.
    assert 'daari_server_tool_cost_usd_total{tool=' not in text0

    metrics.record_server_tool_cost({"web_search": 0.03, "file_search": 0.0025})
    metrics.record_server_tool_cost({"web_search": 0.01})
    metrics.record_server_tool_cost({"web_fetch": 0.0})  # zero-fee omitted
    text = render_prometheus(metrics)
    assert 'daari_server_tool_cost_usd_total{tool="web_search"} 0.04' in text
    assert 'daari_server_tool_cost_usd_total{tool="file_search"} 0.0025' in text
    assert 'tool="web_fetch"' not in text
    snap = metrics.snapshot(include_histograms=True)
    assert snap["server_tool_cost_usd"]["web_search"] == pytest.approx(0.04)
    assert snap["server_tool_cost_usd"]["file_search"] == pytest.approx(0.0025)


def test_ledger_record_increments_tool_cost_from_daari_meta(tmp_path, settings):
    settings = settings.model_copy(
        update={"usage": settings.usage.model_copy(update={"db_path": str(tmp_path / "u.db")})}
    )
    ctx = AppContext.from_settings(settings)
    data = {
        "output": [
            {"type": "web_search_call"},
            {"type": "file_search_call"},
            {"type": "web_fetch_call"},
        ]
    }
    fee, usage = server_tool_fees(data, pricing=settings.pricing)
    assert fee > 0
    assert usage["web_fetch"] == 1  # $0 default — must not inflate counter
    request = InternalRequest(messages=[Message(role="user", content="hi")], model="gpt-4o")
    response = InternalResponse(
        content="ok",
        model="gpt-4o",
        daari_meta=DaariMeta(
            tier="L6",
            executor="frontier",
            model="gpt-4o",
            tool_cost_usd=fee,
            tool_usage=usage,
        ),
    )
    ctx.router._ledger_record(request, response)
    snap = ctx.metrics.snapshot(include_histograms=True)
    prices = resolve_server_tool_prices(settings.pricing)
    assert snap["server_tool_cost_usd"]["web_search"] == pytest.approx(prices["web_search"])
    assert snap["server_tool_cost_usd"]["file_search"] == pytest.approx(prices["file_search"])
    assert "web_fetch" not in snap["server_tool_cost_usd"]

    local = InternalResponse(
        content="local",
        model="llama3.2:3b",
        daari_meta=DaariMeta(tier="L3", executor="ollama", model="llama3.2:3b"),
    )
    ctx.router._ledger_record(request, local)
    snap2 = ctx.metrics.snapshot(include_histograms=True)
    assert snap2["server_tool_cost_usd"] == snap["server_tool_cost_usd"]
