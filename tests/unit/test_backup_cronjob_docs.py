"""backup-restore.md pin for Helm scheduled encrypted backups (#1256)."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKUP_RESTORE = ROOT / "docs/developer/guides/operations/backup-restore.md"


def test_backup_restore_pins_helm_cronjob_encrypted_backups() -> None:
    text = BACKUP_RESTORE.read_text(encoding="utf-8")
    assert "### Helm CronJob" in text
    assert "CronJob" in text
    assert "backup.enabled" in text
    assert "backup.schedule" in text
    assert "--encrypt openssl" in text
