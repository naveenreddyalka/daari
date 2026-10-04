"""Hermetic pin for compact_to_fit_applied in stats docs (#1361)."""

from __future__ import annotations

from pathlib import Path

DOC = (
    Path(__file__).resolve().parents[2]
    / "docs/developer/guides/observability/traces-stats.md"
)


def test_traces_stats_docs_pin_compact_to_fit_applied() -> None:
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
