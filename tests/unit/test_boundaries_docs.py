"""boundaries.md Observe subsection links the Prometheus series (#702)."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DOC = REPO_ROOT / "docs/developer/guides/features/boundaries.md"


def test_boundaries_guide_observe_links_decisions_metric() -> None:
    text = DOC.read_text(encoding="utf-8")
    assert "## Observe" in text
    assert "daari_boundary_decisions_total" in text
    assert "metrics-prometheus.md" in text
