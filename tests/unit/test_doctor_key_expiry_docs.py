"""Doctor-health guide names key_expiry check (#1575)."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOCTOR_HEALTH = ROOT / "docs/developer/guides/operations/doctor-health.md"


def test_doctor_health_documents_key_expiry_checks() -> None:
    text = DOCTOR_HEALTH.read_text(encoding="utf-8")
    assert "doctor `key_expiry`" in text
    assert "key_expiry_warn_days" in text
    assert "doctor `key_expiry_webhook_secret`" in text
    assert "key_expiry_webhook_url" in text
    assert "key_expiry_webhook_secret" in text
