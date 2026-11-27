"""Prometheus / stats counters for the OpenAI regional-processing 1.10× uplift (#2323)."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from daari.gateway.internal import DaariMeta, InternalRequest, InternalResponse, Message
from daari.observability.metrics import Metrics
from daari.observability.prometheus import render_prometheus
from daari.pricing import cost_usd, regional_processing_factor
from daari.router.router import AppContext
from daari.server.app import create_app


def test_prometheus_emits_regional_series_only_when_recorded():
    metrics = Metrics()
    text0 = render_prometheus(metrics)
    assert "# HELP daari_regional_processing_applied_total" in text0
    assert "# TYPE daari_regional_processing_applied_total counter" in text0
    assert "# HELP daari_regional_processing_uplift_usd_total" in text0
    assert "# TYPE daari_regional_processing_uplift_usd_total counter" in text0
    assert "daari_regional_processing_applied_total{" not in text0
    assert "daari_regional_processing_uplift_usd_total{" not in text0

    metrics.record_regional_processing(region="eu", uplift_usd=0.02)
    metrics.record_regional_processing(region="EU ", uplift_usd=0.01)
    metrics.record_regional_processing(region="sg", uplift_usd=0.005)
    text = render_prometheus(metrics)
    assert 'daari_regional_processing_applied_total{region="eu"} 2' in text
    assert 'daari_regional_processing_applied_total{region="sg"} 1' in text
    assert 'daari_regional_processing_uplift_usd_total{region="eu"} 0.03' in text
    assert 'daari_regional_processing_uplift_usd_total{region="sg"} 0.005' in text
    snap = metrics.snapshot(include_histograms=True)
    assert snap["regional_processing_applied"] == {"eu": 2, "sg": 1}
    assert snap["regional_processing_uplift_usd"]["eu"] == pytest.approx(0.03)
    assert snap["regional_processing_uplift_usd"]["sg"] == pytest.approx(0.005)


def test_record_regional_processing_ignores_blank_region():
    metrics = Metrics()
    metrics.record_regional_processing(region="", uplift_usd=1.0)
    metrics.record_regional_processing(region=None, uplift_usd=1.0)
    snap = metrics.snapshot(include_histograms=True)
    assert snap["regional_processing_applied"] == {}
    assert snap["regional_processing_uplift_usd"] == {}


def _ctx(tmp_path, settings) -> AppContext:
    settings = settings.model_copy(
        update={"usage": settings.usage.model_copy(update={"db_path": str(tmp_path / "u.db")})}
    )
    return AppContext.from_settings(settings)


def _frontier(model: str, *, input_tokens: int, output_tokens: int) -> InternalResponse:
    return InternalResponse(
        content="ok",
        model=model,
        daari_meta=DaariMeta(
            tier="L6",
            executor="frontier",
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        ),
    )


@pytest.mark.parametrize("pin", ["us", "ca", "sg", "kr", "gb", "ae"])
def test_ledger_record_attributes_uplift_delta_by_region(tmp_path, settings, pin):
    """Pinned premium model records billed − pre-uplift under the region label."""
    ctx = _ctx(tmp_path, settings)
    request = InternalRequest(
        messages=[Message(role="user", content="hi")], model="gpt-6-luna"
    )
    request.meta.region_pin = pin
    response = _frontier("gpt-6-luna", input_tokens=1_000_000, output_tokens=1_000_000)
    ctx.router._ledger_record(request, response)

    fallback = float(ctx.settings.usage.frontier_price_per_1k_tokens or 0.002)
    base = cost_usd(
        "gpt-6-luna", 1_000_000, 1_000_000, ctx.settings.pricing, fallback_per_1k=fallback
    )
    assert regional_processing_factor(pin, "gpt-6-luna") == pytest.approx(1.10)
    expected_delta = base * 1.10 - base
    assert expected_delta > 0
    snap = ctx.metrics.snapshot(include_histograms=True)
    assert snap["regional_processing_applied"] == {pin: 1}
    assert snap["regional_processing_uplift_usd"][pin] == pytest.approx(expected_delta)
    text = render_prometheus(ctx.metrics)
    assert f'daari_regional_processing_applied_total{{region="{pin}"}} 1' in text
    assert f'daari_regional_processing_uplift_usd_total{{region="{pin}"}}' in text


def test_ledger_record_uses_provider_reported_total_for_delta(tmp_path, settings):
    """A provider-reported cost already includes the 1.10×; delta is billed − billed/1.10."""
    ctx = _ctx(tmp_path, settings)
    request = InternalRequest(
        messages=[Message(role="user", content="hi")], model="gpt-6-astra"
    )
    request.meta.region_pin = "eu"
    response = _frontier("gpt-6-astra", input_tokens=1_000, output_tokens=100)
    response.daari_meta.cost_usd = 1.10
    ctx.router._ledger_record(request, response)
    snap = ctx.metrics.snapshot(include_histograms=True)
    assert snap["regional_processing_applied"] == {"eu": 1}
    assert snap["regional_processing_uplift_usd"]["eu"] == pytest.approx(0.10)


def test_ledger_record_quiet_without_pin_or_premium_model(tmp_path, settings):
    ctx = _ctx(tmp_path, settings)
    unpinned = InternalRequest(
        messages=[Message(role="user", content="hi")], model="gpt-6-luna"
    )
    ctx.router._ledger_record(
        unpinned, _frontier("gpt-6-luna", input_tokens=10_000, output_tokens=1_000)
    )

    pre_cutoff = InternalRequest(
        messages=[Message(role="user", content="hi")], model="gpt-4o-mini"
    )
    pre_cutoff.meta.region_pin = "eu"
    ctx.router._ledger_record(
        pre_cutoff, _frontier("gpt-4o-mini", input_tokens=10_000, output_tokens=1_000)
    )

    anthropic = InternalRequest(
        messages=[Message(role="user", content="hi")], model="claude-sonnet-5-5"
    )
    anthropic.meta.region_pin = "us"
    ctx.router._ledger_record(
        anthropic, _frontier("claude-sonnet-5-5", input_tokens=10_000, output_tokens=1_000)
    )

    local = InternalRequest(
        messages=[Message(role="user", content="hi")], model="gpt-6-luna"
    )
    local.meta.region_pin = "eu"
    ctx.router._ledger_record(
        local,
        InternalResponse(
            content="local",
            model="llama3.2:3b",
            daari_meta=DaariMeta(tier="L3", executor="ollama", model="llama3.2:3b"),
        ),
    )

    snap = ctx.metrics.snapshot(include_histograms=True)
    assert snap["regional_processing_applied"] == {}
    assert snap["regional_processing_uplift_usd"] == {}
    text = render_prometheus(ctx.metrics)
    assert "daari_regional_processing_applied_total{" not in text
    assert "daari_regional_processing_uplift_usd_total{" not in text


@pytest.mark.asyncio
async def test_stats_exposes_regional_processing_maps(settings):
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        before = await client.get("/v1/daari/stats")
        assert before.status_code == 200
        assert before.json()["regional_processing_applied"] == {}
        assert before.json()["regional_processing_uplift_usd"] == {}
        app.state.ctx.metrics.record_regional_processing(region="gb", uplift_usd=0.25)
        after = await client.get("/v1/daari/stats")
    body = after.json()
    assert body["regional_processing_applied"] == {"gb": 1}
    assert body["regional_processing_uplift_usd"]["gb"] == pytest.approx(0.25)
