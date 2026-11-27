"""On-box 7-day performance spike alerts (#2360)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from daari.config.settings import Settings
from daari.observability.budget_alerts import sign_webhook
from daari.observability.metrics import Metrics
from daari.observability.performance_alerts import (
    PerformanceLedger,
    fire_new_alerts,
    open_alerts_for_settings,
)
from daari.observability.prometheus import render_prometheus
from daari.setup.doctor import _check_performance_webhook_secret

NOW = datetime(2026, 11, 27, 12, 0, tzinfo=timezone.utc)


def _settings(tmp_path, **overrides) -> Settings:
    settings = Settings()
    settings.usage.spend.path = str(tmp_path / "spend.sqlite")
    settings.alerts.performance_min_baseline_requests = 4
    settings.alerts.performance_webhook_url = "https://hooks.example/spikes"
    settings.alerts.performance_webhook_secret = "sek"
    for name, value in overrides.items():
        setattr(settings.alerts, name, value)
    return settings


def _ledger(tmp_path, settings: Settings) -> PerformanceLedger:
    ledger = PerformanceLedger(tmp_path / "performance-alerts.sqlite", enabled=True)
    ledger.source_settings = settings
    return ledger


def _seed_quiet_baseline(ledger: PerformanceLedger, *, n: int = 28) -> None:
    for i in range(n):
        ledger.record(
            ts=NOW - timedelta(days=2, hours=i),
            cost_usd=1.0,
            latency_ms=100,
            frontier=True,
        )


def test_spend_spike_fires_and_a_drop_does_not(tmp_path):
    settings = _settings(tmp_path)
    ledger = _ledger(tmp_path, settings)
    _seed_quiet_baseline(ledger)
    ledger.record(
        ts=NOW - timedelta(hours=2),
        cost_usd=40.0,
        latency_ms=100,
        frontier=True,
    )
    alerts = open_alerts_for_settings(ledger, settings, NOW)
    kinds = {row["kind"] for row in alerts}
    assert "spend" in kinds
    assert "traffic" not in kinds

    quiet = _ledger(tmp_path / "drop", settings)
    _seed_quiet_baseline(quiet)
    quiet.record(
        ts=NOW - timedelta(hours=2),
        cost_usd=0.1,
        latency_ms=50,
        frontier=True,
    )
    assert open_alerts_for_settings(quiet, settings, NOW) == []


def test_latency_and_error_rate_spikes(tmp_path):
    settings = _settings(tmp_path, performance_min_baseline_requests=20)
    ledger = _ledger(tmp_path, settings)
    for i in range(20):
        ledger.record(
            ts=NOW - timedelta(days=3, hours=i),
            cost_usd=0.0,
            latency_ms=100,
            error=(i == 0),
        )
    for i in range(4):
        ledger.record(
            ts=NOW - timedelta(hours=1, minutes=i),
            cost_usd=0.0,
            latency_ms=400,
            error=i < 3,
        )
    kinds = {row["kind"] for row in open_alerts_for_settings(ledger, settings, NOW)}
    assert "latency" in kinds
    assert "error_rate" in kinds
    assert "spend" not in kinds


def test_webhook_is_signed_once_per_window(tmp_path):
    settings = _settings(tmp_path)
    ledger = _ledger(tmp_path, settings)
    _seed_quiet_baseline(ledger)
    ledger.record(
        ts=NOW - timedelta(hours=1),
        cost_usd=40.0,
        latency_ms=100,
        frontier=True,
    )
    posted: list[tuple[bytes, dict[str, str]]] = []
    metrics = Metrics()
    first = fire_new_alerts(
        ledger, settings, metrics=metrics, now=NOW, poster=lambda body, headers: posted.append((body, headers))
    )
    second = fire_new_alerts(
        ledger, settings, metrics=metrics, now=NOW, poster=lambda body, headers: posted.append((body, headers))
    )
    assert len(first) == 1
    assert second == []
    assert metrics.performance_alerts.get("spend") == 1
    body, headers = posted[0]
    stamp = headers["X-Daari-Timestamp"]
    assert headers["X-Daari-Signature"] == sign_webhook(body, "sek", stamp)
    text = render_prometheus(metrics)
    assert 'daari_performance_alerts_total{kind="spend"} 1' in text
    assert "spend" in body.decode()


def test_kill_switch_suppresses_open_alerts(tmp_path):
    settings = _settings(tmp_path, performance_enabled=False)
    ledger = _ledger(tmp_path, settings)
    _seed_quiet_baseline(ledger)
    ledger.record(ts=NOW - timedelta(hours=1), cost_usd=40.0, latency_ms=100, frontier=True)
    assert open_alerts_for_settings(ledger, settings, NOW) == []
    assert fire_new_alerts(ledger, settings, now=NOW, poster=lambda *_: None) == []


def test_record_error_samples_only_5xx():
    seen: list[object] = []
    metrics = Metrics()
    metrics.performance_observer = seen.append
    metrics.record_error(503)
    metrics.record_error(400)
    metrics.record_error(None)
    assert seen == [503]


def test_doctor_wants_a_secret_when_the_url_is_set():
    settings = Settings()
    settings.alerts.performance_webhook_url = "https://hooks.example/spikes"
    missing = _check_performance_webhook_secret(settings)
    assert missing.ok is False
    assert missing.optional is True
    settings.alerts.performance_webhook_secret = "sek"
    assert _check_performance_webhook_secret(settings).ok is True


def test_docs_describe_the_dial():
    from pathlib import Path

    text = Path("docs/developer/guides/configuration/budgets-frontier.md").read_text(
        encoding="utf-8"
    )
    assert "performance_enabled" in text
    assert "performance_webhook_url" in text
    assert "prior 7 days" in text
