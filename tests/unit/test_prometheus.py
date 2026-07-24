"""F3: Prometheus exposition format for /metrics (issue #107)."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from daari.observability.metrics import Metrics
from daari.observability.prometheus import render_prometheus
from daari.router.router import AppContext
from daari.server.app import create_app


class TestRenderPrometheus:
    def test_empty_metrics_emits_zeros(self):
        text = render_prometheus(Metrics())
        assert "daari_requests_total" in text
        assert "daari_errors_total 0" in text
        assert "# HELP daari_requests_total" in text
        assert "# TYPE daari_requests_total counter" in text

    def test_tier_labels_and_cache_hits(self):
        metrics = Metrics()
        metrics.record("L3", latency_ms=100)
        metrics.record("L3", latency_ms=200)
        metrics.record("L0", cache_hit=True, latency_ms=1)
        metrics.record_error()
        metrics.record_escalation()
        text = render_prometheus(metrics)
        assert 'daari_requests_total{tier="L3"} 2' in text
        assert 'daari_requests_total{tier="L0"} 1' in text
        assert 'daari_cache_hits_total{tier="L0"} 1' in text
        assert "daari_errors_total 1" in text
        assert "daari_escalations_total 1" in text
        assert "daari_request_latency_ms_sum" in text
        assert 'daari_request_latency_ms_bucket{tier="L3",le="250"}' in text
        assert 'daari_request_latency_ms_bucket{tier="L3",le="+Inf"} 2' in text

    def test_budget_and_false_hit_gauges(self):
        text = render_prometheus(
            Metrics(),
            budget_state={"daily_spend_usd": 0.42, "daily_budget_usd": 1.0, "state": "ok"},
            false_hit_rate=0.05,
        )
        assert "daari_frontier_spend_usd{window=\"daily\"} 0.42" in text
        assert "daari_frontier_budget_usd{window=\"daily\"} 1.0" in text
        assert 'daari_frontier_budget_state{state="ok"} 1' in text
        assert "daari_cache_false_hit_rate 0.05" in text

    def test_guardrail_trips_counter(self):
        metrics = Metrics()
        metrics.record_guardrail("block")
        metrics.record_guardrail("warn")
        text = render_prometheus(metrics)
        assert 'daari_guardrail_trips_total{action="block"} 1' in text
        assert 'daari_guardrail_trips_total{action="warn"} 1' in text


@pytest.mark.asyncio
async def test_metrics_endpoint_open_without_auth(settings):
    settings.observability.prometheus = True
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/metrics")
    assert response.status_code == 200
    assert "text/plain" in response.headers["content-type"]
    assert "daari_requests_total" in response.text


@pytest.mark.asyncio
async def test_metrics_endpoint_requires_auth_when_api_key_set(settings):
    settings.server.api_key = "sekret"
    settings.observability.prometheus = True
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        denied = await client.get("/metrics")
        assert denied.status_code == 401
        ok = await client.get("/metrics", headers={"Authorization": "Bearer sekret"})
    assert ok.status_code == 200
    assert "daari_errors_total" in ok.text


@pytest.mark.asyncio
async def test_metrics_disabled_returns_404(settings):
    settings.observability.prometheus = False
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/metrics")
    assert response.status_code == 404
