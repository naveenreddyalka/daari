"""Cumulative input/output cost USD on Prometheus and /v1/daari/stats (#2189)."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from daari.config.settings import ModelPrice, PricingSettings
from daari.gateway.internal import DaariMeta, InternalRequest, InternalResponse, Message
from daari.observability.metrics import Metrics
from daari.observability.prometheus import render_prometheus
from daari.observability.usage import UsageLedger
from daari.pricing import cost_breakdown
from daari.router.router import AppContext
from daari.server.app import create_app


def _pricing() -> PricingSettings:
    return PricingSettings(
        models={
            "claude-sonnet-5": ModelPrice(
                input_per_1m=3.0,
                output_per_1m=15.0,
                cached_input_per_1m=0.30,
                cache_write_1h_per_1m=3.75,
            )
        }
    )


def test_prometheus_emits_zero_cost_input_output_series():
    text = render_prometheus(Metrics())
    assert "# HELP daari_cost_input_usd_total" in text
    assert "# TYPE daari_cost_input_usd_total counter" in text
    assert "daari_cost_input_usd_total 0" in text
    assert "# HELP daari_cost_output_usd_total" in text
    assert "# TYPE daari_cost_output_usd_total counter" in text
    assert "daari_cost_output_usd_total 0" in text


def test_record_cost_increments_and_sums_to_breakdown_total():
    metrics = Metrics()
    pricing = _pricing()
    parts = cost_breakdown(
        "claude-sonnet-5",
        1_000_000,
        500_000,
        pricing,
        fallback_per_1k=0.002,
        cached_input_tokens=200_000,
        cache_write_tokens=100_000,
        cache_ttl="1h",
        service_tier="priority",
        usage_speed="fast",
    )
    metrics.record_cost(input_usd=parts.input_usd, output_usd=parts.output_usd)
    metrics.record_cost(input_usd=0.0, output_usd=0.0)  # local / zero path
    text = render_prometheus(metrics)
    assert f"daari_cost_input_usd_total {parts.input_usd}" in text
    assert f"daari_cost_output_usd_total {parts.output_usd}" in text
    snap = metrics.snapshot(include_histograms=True)
    assert snap["cost_input_usd"] == pytest.approx(parts.input_usd)
    assert snap["cost_output_usd"] == pytest.approx(parts.output_usd)
    assert snap["cost_input_usd"] + snap["cost_output_usd"] == pytest.approx(parts.total)


@pytest.mark.asyncio
async def test_stats_exposes_cost_input_output_running_totals(settings):
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    metrics = app.state.ctx.metrics
    metrics.record_cost(input_usd=0.04, output_usd=0.08)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/v1/daari/stats")

    assert response.status_code == 200
    body = response.json()
    assert body["cost_input_usd"] == pytest.approx(0.04)
    assert body["cost_output_usd"] == pytest.approx(0.08)


@pytest.mark.asyncio
async def test_ledger_record_accumulates_cost_split_with_multipliers(tmp_path, settings):
    """_ledger_record feeds Metrics from the same breakdown as cost headers (#2189)."""
    settings = settings.model_copy(
        update={
            "pricing": _pricing(),
            "usage": settings.usage.model_copy(update={"db_path": str(tmp_path / "usage.db")}),
        }
    )
    ctx = AppContext.from_settings(settings)
    ctx.router.usage_ledger = UsageLedger(tmp_path / "usage.db")
    request = InternalRequest(
        messages=[Message(role="user", content="hi")],
        model="claude-sonnet-5",
    )
    request.meta.client_id = "key-a"
    response = InternalResponse(
        content="ok",
        model="claude-sonnet-5",
        daari_meta=DaariMeta(
            tier="L6",
            executor="frontier",
            model="claude-sonnet-5",
            input_tokens=1_000_000,
            output_tokens=500_000,
            cached_tokens=200_000,
            cache_write_tokens=100_000,
            service_tier="priority",
            usage_speed="fast",
        ),
    )
    expected = cost_breakdown(
        "claude-sonnet-5",
        1_000_000,
        500_000,
        settings.pricing,
        fallback_per_1k=float(settings.usage.frontier_price_per_1k_tokens or 0.002),
        cached_input_tokens=200_000,
        cache_write_tokens=100_000,
        cache_ttl=None,
        service_tier="priority",
        usage_speed="fast",
    )
    ctx.router._ledger_record(request, response)
    snap = ctx.metrics.snapshot(include_histograms=True)
    assert snap["cost_input_usd"] == pytest.approx(expected.input_usd)
    assert snap["cost_output_usd"] == pytest.approx(expected.output_usd)

    local = InternalResponse(
        content="local",
        model="llama3.2:3b",
        daari_meta=DaariMeta(tier="L3", executor="ollama", model="llama3.2:3b"),
    )
    ctx.router._ledger_record(request, local)
    snap2 = ctx.metrics.snapshot(include_histograms=True)
    assert snap2["cost_input_usd"] == pytest.approx(expected.input_usd)
    assert snap2["cost_output_usd"] == pytest.approx(expected.output_usd)
