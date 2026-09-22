"""CLI + org-cache docs mention cache invalidate --token (#828)."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_cli_md_documents_cache_invalidate_token() -> None:
    text = (ROOT / "docs/developer/reference/cli.md").read_text(encoding="utf-8")
    assert "invalidate" in text
    assert "--token" in text


def test_org_cache_guide_documents_invalidate_token() -> None:
    text = (ROOT / "docs/developer/guides/features/org-cache.md").read_text(encoding="utf-8")
    assert "cache invalidate --token" in text
    assert "Authorization: Bearer" in text or "Bearer" in text
