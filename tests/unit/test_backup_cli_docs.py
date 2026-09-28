"""cli.md documents backup encrypt / restore-pg flags (#1193)."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_cli_md_documents_backup_encrypt_and_restore_pg() -> None:
    text = (ROOT / "docs/developer/reference/cli.md").read_text(encoding="utf-8")
    assert "--encrypt" in text
    assert "openssl" in text
    assert "age" in text
    assert "DAARI_BACKUP_PASS" in text
    assert "DAARI_BACKUP_AGE_RECIPIENT" in text or "--age-recipient" in text
    assert "--restore-pg" in text
    assert "--require-pg-dump" in text
    assert "backup-restore.md" in text
