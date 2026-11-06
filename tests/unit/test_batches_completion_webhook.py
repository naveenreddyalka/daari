"""Org-default batches completion webhook (#2077/#2103): naming, doctor, rotation."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml
from typer.testing import CliRunner

from daari.cli.app import app as cli_app
from daari.config.settings import AlertSettings, Settings
from daari.observability.webhook_secrets import rotate_webhook_secret_in_config
from daari.security.offline_mode import offline_mode_findings
from daari.setup.doctor import _check_batches_completion_webhook_secret, _check_webhook_secret_previous_stale

BUDGETS_DOC = Path("docs/developer/guides/configuration/budgets-frontier.md")
DOCTOR_HEALTH = Path("docs/developer/guides/operations/doctor-health.md")


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


def test_rotate_batches_family(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text(
        "alerts:\n  batches_completion_webhook_secret: old-secret\n",
        encoding="utf-8",
    )
    moment = datetime(2026, 11, 6, 12, 0, tzinfo=timezone.utc)
    result = rotate_webhook_secret_in_config(
        path, family="batches", new_secret="new-secret", now=moment
    )
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert loaded["alerts"]["batches_completion_webhook_secret"] == "new-secret"
    assert loaded["alerts"]["batches_completion_webhook_secret_previous"] == "old-secret"
    assert (
        loaded["alerts"]["batches_completion_webhook_secret_rotated_at"]
        == moment.isoformat()
    )
    assert result["had_previous"] is True
    assert result["family"] == "batches"


def test_cli_rotate_secret_batches(tmp_path, monkeypatch):
    path = tmp_path / "config.yaml"
    path.write_text(
        "alerts:\n  batches_completion_webhook_secret: old\n",
        encoding="utf-8",
    )
    settings = Settings()
    settings.enterprise.audit_path = str(tmp_path / "audit.sqlite3")
    monkeypatch.setattr("daari.cli.app.get_settings", lambda: settings)
    runner = CliRunner(env={"NO_COLOR": "1", "TERM": "dumb", "COLUMNS": "120"})
    result = runner.invoke(
        cli_app,
        ["alerts", "rotate-secret", "batches", "--secret", "new", "--config", str(path)],
    )
    assert result.exit_code == 0, result.output
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert loaded["alerts"]["batches_completion_webhook_secret"] == "new"
    assert loaded["alerts"]["batches_completion_webhook_secret_previous"] == "old"


def test_cli_rejects_unknown_webhook_family(tmp_path, monkeypatch):
    path = tmp_path / "config.yaml"
    path.write_text("alerts: {}\n", encoding="utf-8")
    settings = Settings()
    settings.enterprise.audit_path = str(tmp_path / "audit.sqlite3")
    monkeypatch.setattr("daari.cli.app.get_settings", lambda: settings)
    runner = CliRunner(env={"NO_COLOR": "1", "TERM": "dumb", "COLUMNS": "120"})
    result = runner.invoke(
        cli_app,
        ["alerts", "rotate-secret", "not-a-family", "--secret", "x", "--config", str(path)],
    )
    assert result.exit_code == 1
    assert "family must be" in result.output
    assert "batches" in result.output


def test_doctor_tips_stale_batches_previous(settings: Settings):
    settings.alerts.batches_completion_webhook_secret_previous = "old"
    settings.alerts.batches_completion_webhook_secret_rotated_at = (
        datetime.now(timezone.utc) - timedelta(days=10)
    ).isoformat()
    tip = _check_webhook_secret_previous_stale(settings)
    assert tip is not None
    assert "batches" in tip.detail


def test_docs_list_batches_webhook_family():
    budgets = BUDGETS_DOC.read_text()
    assert "rotate-secret" in budgets
    assert "batches" in budgets
    health = DOCTOR_HEALTH.read_text()
    assert "batches_completion_webhook_secret" in health
