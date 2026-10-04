"""Hermetic pin for compact_to_fit_applied in stats docs (#1361)."""

from __future__ import annotations

from pathlib import Path

DOC = (
    Path(__file__).resolve().parents[2]
    / "docs/developer/guides/observability/traces-stats.md"
)


def test_traces_stats_docs_pin_mcp_grant_denied() -> None:
    text = DOC.read_text(encoding="utf-8")
    assert "mcp_grant_denied" in text
    lower = text.lower()
    assert "require_key_access_defined" in text or "grant" in lower
    assert "initialize" in lower or "tools/list" in lower or "tools/call" in lower
    text = DOC.read_text(encoding="utf-8")
    assert "compact_to_fit_applied" in text
    lower = text.lower()
    assert "trim" in lower or "message count" in lower
    assert "increment" in lower or "increments" in lower


def test_traces_stats_docs_pin_daari_meta_compact_to_fit() -> None:
    text = DOC.read_text(encoding="utf-8")
    assert "daari_meta.compact_to_fit" in text or (
        "compact_to_fit" in text and "daari_meta" in text
    )
    assert "messages_before" in text
    assert "messages_after" in text


HEADERS = Path(__file__).resolve().parents[2] / "docs/developer/reference/headers.md"


def test_headers_docs_pin_x_daari_meta_compact_to_fit() -> None:
    text = HEADERS.read_text(encoding="utf-8")
    assert "X-Daari-Meta" in text
    assert "compact_to_fit" in text
    assert "messages_before" in text
    assert "messages_after" in text
