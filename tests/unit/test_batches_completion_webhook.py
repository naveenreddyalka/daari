"""Org-default batches completion webhook (#2077): naming, doctor, offline."""

from __future__ import annotations

from daari.config.settings import AlertSettings, Settings
from daari.security.offline_mode import offline_mode_findings
from daari.setup.doctor import _check_batches_completion_webhook_secret


def test_alert_settings_default_batches_completion_webhook_off():
    alerts = AlertSettings()
    assert alerts.batches_completion_webhook_url == ""
    assert alerts.batches_completion_webhook_secret == ""
    assert alerts.batches_completion_webhook_secret_previous == ""
    assert alerts.batches_completion_webhook_secret_rotated_at == ""


def test_legacy_batch_keys_map_to_batches():
    alerts = AlertSettings.model_validate(
        {
            "batch_completion_webhook_url": "https://hooks.example/legacy",
            "batch_completion_webhook_secret": "legacy-sec",
            "batch_completion_webhook_secret_previous": "old",
            "batch_completion_webhook_secret_rotated_at": "2026-01-01T00:00:00+00:00",
        }
    )
    assert alerts.batches_completion_webhook_url == "https://hooks.example/legacy"
    assert alerts.batches_completion_webhook_secret == "legacy-sec"
    assert alerts.batches_completion_webhook_secret_previous == "old"
    assert alerts.batches_completion_webhook_secret_rotated_at == "2026-01-01T00:00:00+00:00"


def test_doctor_batches_completion_webhook_without_secret_warns():
    settings = Settings()
    settings.alerts.batches_completion_webhook_url = "https://hooks.example/batches"
    settings.alerts.batches_completion_webhook_secret = ""
    result = _check_batches_completion_webhook_secret(settings)
    assert result.ok is False
    assert result.optional is True
    assert "batches_completion_webhook_url" in result.detail
    assert "batches_completion_webhook_secret" in result.detail
    assert "secret://" in result.detail


def test_doctor_batches_completion_webhook_with_secret_ok():
    settings = Settings()
    settings.alerts.batches_completion_webhook_url = "https://hooks.example/batches"
    settings.alerts.batches_completion_webhook_secret = "whsec_test"
    result = _check_batches_completion_webhook_secret(settings)
    assert result.ok is True


def test_doctor_batches_completion_webhook_empty_url_ok():
    settings = Settings()
    settings.alerts.batches_completion_webhook_url = ""
    settings.alerts.batches_completion_webhook_secret = ""
    result = _check_batches_completion_webhook_secret(settings)
    assert result.ok is True


def test_offline_mode_findings_include_batches_webhook():
    settings = Settings(
        security={"offline_mode": True},
        alerts={"batches_completion_webhook_url": "https://hooks.example/batches"},
    )
    findings = offline_mode_findings(settings)
    joined = "\n".join(findings)
    assert "alerts.batches_completion_webhook_url" in joined


def test_apply_settings_reads_batches_fields():
    from daari.gateway.batches import BatchStore
    from daari.observability.batch_webhooks import apply_batch_webhook_settings

    settings = Settings()
    settings.alerts.batches_completion_webhook_url = "https://hooks.example/b"
    settings.alerts.batches_completion_webhook_secret = "sec"
    settings.alerts.batches_completion_webhook_secret_previous = "prev"
    store = BatchStore()
    apply_batch_webhook_settings(store, settings)
    assert store.completion_webhook_url == "https://hooks.example/b"
    assert store.completion_webhook_secret == "sec"
    assert store.completion_webhook_secret_previous == "prev"
