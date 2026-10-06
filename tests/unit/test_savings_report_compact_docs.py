"""Hermetic pin for compact_to_fit_tokens_dropped in savings-report.md (#1432)."""

from __future__ import annotations

from pathlib import Path

DOC = (
    Path(__file__).resolve().parents[2]
    / "docs/developer/guides/observability/savings-report.md"
)


def test_savings_report_docs_pin_compact_to_fit_tokens_dropped() -> None:
    text = DOC.read_text(encoding="utf-8")
    assert "compact_to_fit_tokens_dropped" in text
    assert "tokens_before" in text
    assert "tokens_after" in text
    assert "traces-stats.md" in text or "traces and stats" in text.lower()
    assert "routing-tiers.md" in text
