"""Opt-in team label on request/error Prometheus series (#1997)."""

from __future__ import annotations

from daari.observability.metrics import Metrics, team_metric_label
from daari.observability.prometheus import render_prometheus


def test_team_metric_label_bounds_to_allowlist():
    allowed = frozenset({"acme", "beta"})
    assert team_metric_label(None, allowed=allowed) == "-"
    assert team_metric_label("", allowed=allowed) == "-"
    assert team_metric_label("acme", allowed=allowed) == "acme"
    assert team_metric_label("evil", allowed=allowed) == "-"
    assert team_metric_label("  acme  ", allowed=allowed) == "acme"


def test_team_metrics_off_byte_identical_to_baseline():
    """When team_metrics is off, exposition matches the legacy shape (#1997)."""
    baseline = Metrics()
    baseline.record("L3", latency_ms=100)
    baseline.record("L6", latency_ms=200)
    baseline.record_error(status=503)
    baseline.record_error(status=429)

    opted = Metrics()
    opted.configure_team_metrics(enabled=False, allowed=frozenset({"acme"}))
    opted.record("L3", latency_ms=100, team="acme")
    opted.record("L6", latency_ms=200, team="acme")
    opted.record_error(status=503, team="acme")
    opted.record_error(status=429, team="acme")

    assert render_prometheus(opted, team_metrics=False) == render_prometheus(baseline)


def test_team_metrics_on_adds_team_label_and_sums_match_tiers():
    metrics = Metrics()
    metrics.configure_team_metrics(enabled=True, allowed=frozenset({"acme", "beta"}))
    metrics.record("L3", latency_ms=50, team="acme")
    metrics.record("L3", latency_ms=60, team="beta")
    metrics.record("L6", latency_ms=100, team="acme")
    metrics.record("L6", latency_ms=110)  # empty → "-"
    metrics.record("L3", latency_ms=70, team="unknown-from-request")  # not allowed → "-"
    metrics.record_error(status=503, team="acme")
    metrics.record_error(status=503, team="beta")
    metrics.record_error(status=429, team="nosuch")

    text = render_prometheus(metrics, team_metrics=True)

    assert 'daari_requests_total{tier="L3",team="acme"} 1' in text
    assert 'daari_requests_total{tier="L3",team="beta"} 1' in text
    assert 'daari_requests_total{tier="L3",team="-"} 1' in text
    assert 'daari_requests_total{tier="L6",team="acme"} 1' in text
    assert 'daari_requests_total{tier="L6",team="-"} 1' in text
    # No unbounded / raw request team values.
    assert 'team="unknown-from-request"' not in text
    assert 'team="nosuch"' not in text
    # Legacy tier-only series must not appear when team_metrics is on.
    assert 'daari_requests_total{tier="L3"} 3' not in text
    assert 'daari_requests_total{tier="L6"} 2' not in text

    assert 'daari_errors_total{status="503",team="acme"} 1' in text
    assert 'daari_errors_total{status="503",team="beta"} 1' in text
    assert 'daari_errors_total{status="429",team="-"} 1' in text
    assert 'daari_errors_total{status="503"} 2' not in text

    # Latency histograms stay team-less (cardinality guard).
    assert "daari_request_latency_ms_bucket{tier=" in text
    assert "daari_request_latency_ms_bucket{tier=" in text
    assert 'daari_request_latency_ms_bucket{tier="L3",team=' not in text
    assert 'daari_request_latency_ms_sum{tier="L3",team=' not in text


def test_team_metrics_on_empty_emits_team_dash_zero():
    text = render_prometheus(Metrics(), team_metrics=True)
    assert 'daari_requests_total{team="-"} 0' in text
    assert 'daari_errors_total{status="0",team="-"} 0' in text


def test_team_metrics_reads_spend_context_team():
    from daari.observability.spend import SpendContext, bind_spend_context

    metrics = Metrics()
    metrics.configure_team_metrics(enabled=True, allowed=frozenset({"acme"}))
    token = bind_spend_context(SpendContext(team_id="acme"))
    try:
        metrics.record("L3", latency_ms=10)
        metrics.record_error(status=500)
    finally:
        from daari.observability.spend import _spend_ctx

        _spend_ctx.reset(token)

    text = render_prometheus(metrics, team_metrics=True)
    assert 'daari_requests_total{tier="L3",team="acme"} 1' in text
    assert 'daari_errors_total{status="500",team="acme"} 1' in text


def test_observability_team_metrics_setting_default_off():
    from daari.config.settings import ObservabilitySettings

    assert ObservabilitySettings().team_metrics is False


def test_metrics_prometheus_docs_include_team_promql():
    from pathlib import Path

    doc = (
        Path(__file__).resolve().parents[2]
        / "docs/developer/guides/observability/metrics-prometheus.md"
    )
    body = doc.read_text(encoding="utf-8")
    assert "sum by (team) (rate(daari_requests_total[5m]))" in body
    assert "observability.team_metrics" in body
    assert "team-less" in body.lower()
