"""Opt-in cardinality-capped per-key label on Prometheus series (#2199)."""

from __future__ import annotations

from daari.observability.metrics import Metrics, key_metric_label
from daari.observability.prometheus import render_prometheus


def test_key_metric_label_placeholder_and_overflow():
    seen: dict[str, None] = {}
    assert key_metric_label(None, max_keys=2, seen=seen) == "-"
    assert key_metric_label("", max_keys=2, seen=seen) == "-"
    assert key_metric_label("  k1  ", max_keys=2, seen=seen) == "k1"
    assert key_metric_label("k2", max_keys=2, seen=seen) == "k2"
    assert key_metric_label("k3", max_keys=2, seen=seen) == "-overflow"
    assert key_metric_label("k1", max_keys=2, seen=seen) == "k1"
    assert list(seen.keys()) == ["k1", "k2"]


def test_key_metrics_off_byte_identical_to_baseline():
    """When key_metrics is off, exposition matches the legacy shape (#2199)."""
    baseline = Metrics()
    baseline.record("L3", latency_ms=100, input_tokens=10, output_tokens=5)
    baseline.record_cost(input_usd=0.01, output_usd=0.02)

    opted = Metrics()
    opted.configure_key_metrics(enabled=False, max_keys=100)
    opted.record("L3", latency_ms=100, input_tokens=10, output_tokens=5, key="vk_abc")
    opted.record_cost(input_usd=0.01, output_usd=0.02, key="vk_abc")

    assert render_prometheus(opted, key_metrics=False) == render_prometheus(baseline)


def test_key_metrics_on_adds_key_label_on_requests_tokens_cost():
    metrics = Metrics()
    metrics.configure_key_metrics(enabled=True, max_keys=100)
    metrics.record("L3", latency_ms=50, input_tokens=3, output_tokens=2, key="vk_a")
    metrics.record("L3", latency_ms=60, input_tokens=1, output_tokens=1, key="vk_b")
    metrics.record("L6", latency_ms=100)  # unauthenticated → "-"
    metrics.record_cost(input_usd=0.04, output_usd=0.08, key="vk_a")
    metrics.record_cost(input_usd=0.01, output_usd=0.02, key="vk_b")

    text = render_prometheus(metrics, key_metrics=True)

    assert 'daari_requests_total{tier="L3",key="vk_a"} 1' in text
    assert 'daari_requests_total{tier="L3",key="vk_b"} 1' in text
    assert 'daari_requests_total{tier="L6",key="-"} 1' in text
    assert 'daari_requests_total{tier="L3"} 2' not in text

    assert 'daari_tokens_total{modality="chat",tier="L3",direction="input",key="vk_a"} 3' in text
    assert 'daari_tokens_total{modality="chat",tier="L3",direction="output",key="vk_a"} 2' in text
    assert 'daari_tokens_total{modality="chat",tier="L3",direction="input",key="vk_b"} 1' in text
    assert 'daari_tokens_total{modality="chat",tier="L3",direction="input"} 4' not in text

    assert 'daari_cost_input_usd_total{key="vk_a"} 0.04' in text
    assert 'daari_cost_output_usd_total{key="vk_a"} 0.08' in text
    assert 'daari_cost_input_usd_total{key="vk_b"} 0.01' in text
    assert "daari_cost_input_usd_total 0.05" not in text

    # Latency histograms stay key-less (cardinality guard).
    assert 'daari_request_latency_ms_bucket{tier="L3",le=' in text
    assert 'daari_request_latency_ms_bucket{tier="L3",key=' not in text
    assert 'daari_request_latency_ms_sum{tier="L3",key=' not in text


def test_key_metrics_overflow_bucket_after_cap():
    metrics = Metrics()
    metrics.configure_key_metrics(enabled=True, max_keys=2)
    metrics.record("L3", latency_ms=10, key="k1")
    metrics.record("L3", latency_ms=10, key="k2")
    metrics.record("L3", latency_ms=10, key="k3")
    metrics.record("L3", latency_ms=10, key="k1")  # still exact

    text = render_prometheus(metrics, key_metrics=True)
    assert 'daari_requests_total{tier="L3",key="k1"} 2' in text
    assert 'daari_requests_total{tier="L3",key="k2"} 1' in text
    assert 'daari_requests_total{tier="L3",key="-overflow"} 1' in text
    assert 'key="k3"' not in text


def test_key_metrics_on_empty_emits_key_dash_zero():
    text = render_prometheus(Metrics(), key_metrics=True)
    assert 'daari_requests_total{key="-"} 0' in text
    assert 'daari_tokens_total{key="-"} 0' in text
    assert 'daari_cost_input_usd_total{key="-"} 0.0' in text
    assert 'daari_cost_output_usd_total{key="-"} 0.0' in text


def test_key_metrics_reads_spend_context_key_id():
    from daari.observability.spend import SpendContext, bind_spend_context

    metrics = Metrics()
    metrics.configure_key_metrics(enabled=True, max_keys=10)
    token = bind_spend_context(SpendContext(key_id="vk_ctx"))
    try:
        metrics.record("L3", latency_ms=10, input_tokens=4, output_tokens=1)
        metrics.record_cost(input_usd=0.001, output_usd=0.002)
    finally:
        from daari.observability.spend import _spend_ctx

        _spend_ctx.reset(token)

    text = render_prometheus(metrics, key_metrics=True)
    assert 'daari_requests_total{tier="L3",key="vk_ctx"} 1' in text
    assert 'daari_tokens_total{modality="chat",tier="L3",direction="input",key="vk_ctx"} 4' in text
    assert 'daari_cost_input_usd_total{key="vk_ctx"} 0.001' in text


def test_observability_key_metrics_settings_defaults():
    from daari.config.settings import ObservabilitySettings

    obs = ObservabilitySettings()
    assert obs.key_metrics is False
    assert obs.key_metrics_max_keys == 100


def test_metrics_prometheus_docs_include_key_promql():
    from pathlib import Path

    doc = (
        Path(__file__).resolve().parents[2]
        / "docs/developer/guides/observability/metrics-prometheus.md"
    )
    body = doc.read_text(encoding="utf-8")
    assert "sum by (key) (rate(daari_requests_total[5m]))" in body
    assert "observability.key_metrics" in body
    assert "key_metrics_max_keys" in body
    assert "-overflow" in body
    assert "key-less" in body.lower() or "keyless" in body.lower()


def test_doctor_tip_when_key_metrics_enabled(settings):
    from daari.setup.doctor import _check_key_metrics, run_doctor

    settings.observability.key_metrics = True
    settings.observability.key_metrics_max_keys = 50
    row = _check_key_metrics(settings)
    assert row is not None
    assert row.name == "key_metrics"
    assert row.ok is True
    assert "cardinality" in row.detail.lower()
    assert "50" in row.detail or "max_keys" in row.detail.lower()

    settings.observability.key_metrics = False
    assert _check_key_metrics(settings) is None
    rows = run_doctor(settings)
    assert not any(r.name == "key_metrics" for r in rows)


def test_grafana_dashboard_includes_top_keys_panel():
    import json
    from pathlib import Path

    payload = json.loads(
        Path("deploy/grafana/daari-dashboard.json").read_text(encoding="utf-8")
    )
    panel = next(
        (p for p in payload["panels"] if "top" in p.get("title", "").lower() and "key" in p.get("title", "").lower()),
        None,
    )
    assert panel is not None, "expected a top-keys panel in daari-dashboard.json"
    exprs = [t.get("expr", "") for t in panel.get("targets", [])]
    assert any("by (key)" in expr and "daari_requests_total" in expr for expr in exprs)
