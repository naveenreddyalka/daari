"""Doctor-health documents backup / encrypt tip (#1196)."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOCTOR_HEALTH = ROOT / "docs/developer/guides/operations/doctor-health.md"


def test_doctor_health_documents_backup_plaintext_encrypt_tip() -> None:
    text = DOCTOR_HEALTH.read_text(encoding="utf-8")
    assert "doctor `backup`" in text
    assert "plaintext" in text
    assert "--encrypt openssl" in text
    assert "age" in text
    assert "backup-restore.md" in text
