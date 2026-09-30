"""Doctor-health documents header_policy empty-rules tip (#1247)."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOCTOR_HEALTH = ROOT / "docs/developer/guides/operations/doctor-health.md"


def test_doctor_health_documents_header_policy_empty_rules_tip() -> None:
    text = DOCTOR_HEALTH.read_text(encoding="utf-8")
    assert "doctor `header_policy`" in text
    assert "enabled" in text
    assert "required" in text and "deny" in text and "allow" in text
    assert "empty" in text
    assert "auth-and-keys.md" in text or "config.md" in text
