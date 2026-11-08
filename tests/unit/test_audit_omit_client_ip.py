"""Opt-in omit requester client_ip from enterprise audit events (#2136)."""

from __future__ import annotations

from pathlib import Path

from daari.config.settings import Settings
from daari.enterprise.audit import (
    OMITTED_CLIENT_IP,
    AuditLog,
    record_auth_throttled,
)
from daari.setup.doctor import _check_audit_omit_client_ip


ROOT = Path(__file__).resolve().parents[2]


def test_settings_omit_client_ip_defaults_false() -> None:
    settings = Settings()
    assert settings.security.audit.omit_client_ip is False


def test_record_auth_throttled_keeps_client_ip_by_default(tmp_path) -> None:
    audit = AuditLog(tmp_path / "audit.sqlite3")
    record_auth_throttled(
        audit,
        client_ip="203.0.113.50",
        failures=10,
        retry_after=30,
    )
    rows = audit.list(action="auth.throttled")
    assert len(rows) == 1
    assert rows[0]["actor"] == "203.0.113.50"
    assert rows[0]["detail"]["client_ip"] == "203.0.113.50"


def test_record_auth_throttled_omits_client_ip_when_enabled(tmp_path) -> None:
    audit = AuditLog(tmp_path / "audit.sqlite3")
    record_auth_throttled(
        audit,
        client_ip="203.0.113.50",
        failures=10,
        retry_after=30,
        omit_client_ip=True,
    )
    rows = audit.list(action="auth.throttled")
    assert len(rows) == 1
    assert rows[0]["actor"] == OMITTED_CLIENT_IP
    assert rows[0]["detail"]["client_ip"] == OMITTED_CLIENT_IP
    assert "203.0.113.50" not in rows[0]["actor"]
    assert "203.0.113.50" not in str(rows[0]["detail"])


def test_doctor_tip_absent_by_default(settings) -> None:
    assert _check_audit_omit_client_ip(settings) is None


def test_doctor_tip_when_omit_enabled(settings) -> None:
    settings.security.audit.omit_client_ip = True
    tip = _check_audit_omit_client_ip(settings)
    assert tip is not None
    assert tip.ok is True
    assert tip.optional is True
    assert "omit_client_ip" in tip.detail
    assert OMITTED_CLIENT_IP in tip.detail


def test_config_documents_omit_client_ip() -> None:
    config = (ROOT / "docs/developer/reference/config.md").read_text(encoding="utf-8")
    assert "security.audit.omit_client_ip" in config
    assert "[omitted]" in config or "omit" in config.lower()


def test_doctor_health_docs_mention_audit_omit_client_ip() -> None:
    text = (ROOT / "docs/developer/guides/operations/doctor-health.md").read_text(
        encoding="utf-8"
    )
    assert "audit_omit_client_ip" in text
    assert "security.audit.omit_client_ip" in text
