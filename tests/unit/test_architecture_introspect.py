"""Docs contract: ARCHITECTURE HTTP table lists RFC 7662 introspect (#665)."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ARCHITECTURE = ROOT / "docs" / "ARCHITECTURE.md"


def test_architecture_http_table_lists_post_introspect():
    text = ARCHITECTURE.read_text(encoding="utf-8")
    assert "| `POST` | `/introspect` |" in text
    assert "RFC 7662" in text
