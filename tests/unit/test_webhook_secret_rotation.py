"""Webhook signing-secret rotation with dual-secret grace (#1680)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import yaml
from typer.testing import CliRunner

from daari.cli.app import app as cli_app
from daari.config.settings import Settings
from daari.enterprise.audit import AuditLog
from daari.observability.budget_alerts import (
    BudgetAlerter,
    sign_webhook,
    signature_header_value,
    verify_webhook_signature,
)
from daari.observability.webhook_secrets import rotate_webhook_secret_in_config
from daari.setup.doctor import _check_webhook_secret_previous_stale, run_doctor

DOCTOR_HEALTH = Path("docs/developer/guides/operations/doctor-health.md")
BUDGETS_DOC = Path("docs/developer/guides/configuration/budgets-frontier.md")


def test_dual_verify_accepts_current_or_previous():
    body = b'{"scope":"key","threshold":0.8}'
    ts = str(int(datetime.now(timezone.utc).timestamp()))
    current = "whsec_new"
    previous = "whsec_old"
    header = signature_header_value(
        body, current, ts, previous_secret=previous
    )
    assert "," in header
    assert verify_webhook_signature(
        body, header, current, ts, previous_secret=previous, now=int(ts)
    )
    # Receiver that only knows previous still accepts the dual header.
    assert verify_webhook_signature(
        body, header.split(",")[1], previous, ts, now=int(ts)
    )
    # Receiver that only knows current accepts the first digest.
    assert verify_webhook_signature(
        body, header.split(",")[0], current, ts, now=int(ts)
    )
    assert not verify_webhook_signature(
        body, header, "whsec_other", ts, previous_secret="", now=int(ts)
    )


def test_sign_uses_current_only_when_no_previous():
    body = b"{}"
    ts = "1756944000"
    assert signature_header_value(body, "sec", ts) == sign_webhook(body, "sec", ts)


def test_budget_alerter_sends_dual_signature(tmp_path):
    posted: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        posted.append(request)
        return httpx.Response(204)

    alerter = BudgetAlerter(
        webhook_url="https://hooks.example/budget",
        webhook_secret="whsec_new",
        webhook_secret_previous="whsec_old",
        transport=httpx.MockTransport(handler),
    )
    body = {"scope": "key", "id": "k1", "threshold": 0.8, "window": "daily"}
    alerter.deliver(body)
    assert len(posted) == 1
    sig = posted[0].headers["X-Daari-Signature"]
    ts = posted[0].headers["X-Daari-Timestamp"]
    assert "," in sig
    assert verify_webhook_signature(
        posted[0].content,
        sig,
        "whsec_new",
        ts,
        previous_secret="whsec_old",
        now=int(ts),
    )


def test_rotate_webhook_secret_in_config(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text(
        "alerts:\n  budget_webhook_secret: old-secret\n",
        encoding="utf-8",
    )
    moment = datetime(2026, 10, 16, 12, 0, tzinfo=timezone.utc)
    result = rotate_webhook_secret_in_config(
        path, family="budget", new_secret="new-secret", now=moment
    )
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert loaded["alerts"]["budget_webhook_secret"] == "new-secret"
    assert loaded["alerts"]["budget_webhook_secret_previous"] == "old-secret"
    assert loaded["alerts"]["budget_webhook_secret_rotated_at"] == moment.isoformat()
    assert result["had_previous"] is True


def test_cli_rotate_secret_writes_audit(tmp_path, monkeypatch):
    path = tmp_path / "config.yaml"
    path.write_text(
        "alerts:\n  key_expiry_webhook_secret: old-key\n",
        encoding="utf-8",
    )
    settings = Settings()
    settings.enterprise.audit_path = str(tmp_path / "audit.sqlite3")
    monkeypatch.setattr("daari.cli.app.get_settings", lambda: settings)
    runner = CliRunner(env={"NO_COLOR": "1", "TERM": "dumb", "COLUMNS": "120"})
    result = runner.invoke(
        cli_app,
        ["alerts", "rotate-secret", "key-expiry", "--secret", "new-key", "--config", str(path)],
    )
    assert result.exit_code == 0, result.output
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert loaded["alerts"]["key_expiry_webhook_secret"] == "new-key"
    assert loaded["alerts"]["key_expiry_webhook_secret_previous"] == "old-key"
    rows = AuditLog(settings.enterprise.audit_path).list(
        limit=10, action="alerts.rotate_secret"
    )
    assert rows
    assert rows[0]["action"] == "alerts.rotate_secret"
    assert rows[0]["detail"].get("family") == "key-expiry"


def test_doctor_tips_stale_previous(settings: Settings):
    settings.alerts.budget_webhook_secret_previous = "old"
    settings.alerts.budget_webhook_secret_rotated_at = (
        datetime.now(timezone.utc) - timedelta(days=10)
    ).isoformat()
    tip = _check_webhook_secret_previous_stale(settings)
    assert tip is not None
    assert tip.name == "webhook_secret_previous"
    assert tip.ok is False
    assert tip.optional is True


def test_doctor_silent_when_previous_fresh(settings: Settings):
    settings.alerts.budget_webhook_secret_previous = "old"
    settings.alerts.budget_webhook_secret_rotated_at = datetime.now(timezone.utc).isoformat()
    assert _check_webhook_secret_previous_stale(settings) is None


def test_run_doctor_includes_stale_tip(settings: Settings):
    settings.alerts.key_expiry_webhook_secret_previous = "old"
    settings.alerts.key_expiry_webhook_secret_rotated_at = ""
    names = [r.name for r in run_doctor(settings, httpx_client=None)]
    assert "webhook_secret_previous" in names


def test_docs_mention_rotation():
    budgets = BUDGETS_DOC.read_text()
    assert "rotate-secret" in budgets
    assert "webhook_secret_previous" in budgets
    health = DOCTOR_HEALTH.read_text()
    assert "doctor `webhook_secret_previous`" in health
