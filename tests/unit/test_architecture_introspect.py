"""Docs contract: ARCHITECTURE HTTP table lists RFC 7662 introspect (#665)."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ARCHITECTURE = ROOT / "docs" / "ARCHITECTURE.md"


def test_architecture_http_table_lists_post_introspect():
    text = ARCHITECTURE.read_text(encoding="utf-8")
    assert "| `POST` | `/introspect` |" in text
    assert "RFC 7662" in text


def test_architecture_mentions_compact_to_fit_token_fields() -> None:
    text = ARCHITECTURE.read_text(encoding="utf-8")
    lower = text.lower()
    assert "compact_to_fit" in text or "compact-to-fit" in lower
    assert "tokens_before" in text
    assert "tokens_after" in text
