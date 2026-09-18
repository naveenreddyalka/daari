"""traces-stats.md documents soft_warnings/rejects cliff maps (#682)."""

from __future__ import annotations

from pathlib import Path

DOC = Path(__file__).resolve().parents[2] / "docs/developer/guides/observability/traces-stats.md"


def test_traces_stats_docs_mention_cliff_maps() -> None:
    text = DOC.read_text(encoding="utf-8")
    assert "soft_warnings" in text
    assert "rejects" in text
    assert "backend_summary" in text
    assert "metrics-prometheus.md" in text
