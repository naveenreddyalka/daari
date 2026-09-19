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

    def test_ttft_histogram_by_tier(self):
        metrics = Metrics()
        metrics.record_ttft("L3", ttft_ms=40)
        metrics.record_ttft("L3", ttft_ms=80)
        metrics.record_ttft("L6", ttft_ms=300)
        text = render_prometheus(metrics)
        assert "# TYPE daari_ttft_ms histogram" in text
        assert 'daari_ttft_ms_bucket{tier="L3",le="50"} 1' in text
        assert 'daari_ttft_ms_bucket{tier="L3",le="100"} 2' in text
        assert 'daari_ttft_ms_sum{tier="L3"} 120' in text
        assert 'daari_ttft_ms_count{tier="L3"} 2' in text
        assert 'daari_ttft_ms_count{tier="L6"} 1' in text
        # Non-stream latency recording alone must not invent TTFT series.
        only_latency = Metrics()
        only_latency.record("L3", latency_ms=100)
        assert "daari_ttft_ms" not in render_prometheus(only_latency)

    def test_budget_and_false_hit_gauges(self):
        text = render_prometheus(
            Metrics(),
            budget_state={"daily_spend_usd": 0.42, "daily_budget_usd": 1.0, "state": "ok"},
            false_hit_rate=0.05,
        )
        assert 'daari_frontier_spend_usd{window="daily"} 0.42' in text
        assert 'daari_frontier_budget_usd{window="daily"} 1.0' in text
        assert 'daari_frontier_budget_state{state="ok"} 1' in text
        assert "daari_cache_false_hit_rate 0.05" in text

    def test_guardrail_trips_counter(self):
        metrics = Metrics()
        metrics.record_guardrail("block")
        metrics.record_guardrail("warn")
        text = render_prometheus(metrics)
        assert 'daari_guardrail_trips_total{action="block"} 1' in text
        assert 'daari_guardrail_trips_total{action="warn"} 1' in text

    def test_boundary_decisions_counter(self):
        """Prometheus must export boundary decisions with stage/label (#691)."""
        metrics = Metrics()
        metrics.record_boundary("tools", "pre")
        metrics.record_boundary("tools", "pre")
        metrics.record_boundary("json", "post")
        text = render_prometheus(metrics)
        assert "# TYPE daari_boundary_decisions_total counter" in text
        assert 'daari_boundary_decisions_total{stage="pre",label="tools"} 2' in text
        assert 'daari_boundary_decisions_total{stage="post",label="json"} 1' in text


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


def test_team_budget_gauges_in_render():
    text = render_prometheus(
        Metrics(),
        team_budgets=[
            {
                "team": "alpha",
                "window": "daily",
                "remaining_usd": 0.6,
                "limit_usd": 1.0,
                "remaining_hours": 12.0,
            }
        ],
    )
    assert 'daari_team_budget_remaining_usd{team="alpha",window="daily"} 0.6' in text
    assert 'daari_team_budget_limit_usd{team="alpha",window="daily"} 1.0' in text
    assert 'daari_team_budget_remaining_hours{team="alpha",window="daily"} 12.0' in text


@pytest.mark.asyncio
async def test_metrics_endpoint_exposes_team_budget_remaining(settings, tmp_path):
    from daari.auth.virtual_keys import BudgetWindow, VirtualKeyStore
    from daari.observability.usage import UsageLedger

    settings.server.api_key = ""
    settings.observability.prometheus = True
    settings.server.virtual_keys.path = str(tmp_path / "vk.sqlite3")
    settings.usage.path = str(tmp_path / "usage.sqlite3")
    store = VirtualKeyStore(settings.virtual_keys_path)
    store.create_team(
        "alpha",
        budget_windows=[BudgetWindow("day", 1.0)],
    )
    store.create("k1", client_id="cid-1", team="alpha")
    ledger = UsageLedger(tmp_path / "usage.sqlite3")
    # $0.40 spend at $0.002 / 1k tokens → 200_000 input tokens
    ledger.record(
        tier="L6",
        client_id="cid-1",
        model="",
        input_tokens=200_000,
        output_tokens=0,
    )

    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    app.state.virtual_key_store = store
    app.state.ctx.virtual_key_store = store
    app.state.ctx.router.usage_ledger = ledger

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/metrics")
    assert response.status_code == 200
    text = response.text
    assert 'daari_team_budget_limit_usd{team="alpha",window="daily"} 1.0' in text
    assert 'daari_team_budget_remaining_usd{team="alpha",window="daily"} 0.6' in text
    assert 'daari_team_budget_remaining_hours{team="alpha",window="daily"}' in text


def test_team_rate_limit_gauges_in_render():
    text = render_prometheus(
        Metrics(),
        team_rate_limits=[
            {"team": "eng", "kind": "rpm", "limit": 10, "remaining": 7},
            {"team": "eng", "kind": "rpd", "limit": 100, "remaining": 40},
        ],
    )
    assert 'daari_team_rate_limit_remaining{team="eng",kind="rpm",scope="team"} 7' in text
    assert 'daari_team_rate_limit_limit{team="eng",kind="rpm",scope="team"} 10' in text
    assert 'daari_team_rate_limit_remaining{team="eng",kind="rpd",scope="team"} 40' in text
    assert 'daari_team_rate_limit_limit{team="eng",kind="rpd",scope="team"} 100' in text
