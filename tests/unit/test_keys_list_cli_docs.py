"""CLI reference documents keys list --status and --idle-days (#1571)."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CLI_MD = ROOT / "docs/developer/reference/cli.md"


def test_cli_md_documents_keys_list_status_and_idle_days() -> None:
    text = CLI_MD.read_text(encoding="utf-8")
    assert "keys list" in text
    assert "--status" in text
    assert "active" in text and "expired" in text and "revoked" in text
    assert "--idle-days" in text
    assert "last_used_at" in text
    assert "virtual-keys.md" in text
