"""Hermetic pin: OpenRouter rebuilt performance-router honesty (#2057)."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
COMPARE = ROOT / "docs/developer/resources/compare-openrouter.md"
INDEX = ROOT / "docs/developer/resources/compare.md"


def test_compare_openrouter_pins_rebuilt_routing() -> None:
    text = COMPARE.read_text(encoding="utf-8")
    lower = text.lower()
    assert "rebuilt" in lower and "provider routing" in lower
    assert "openrouter.ai/blog/announcements/how-we-rebuilt-provider-routing" in text
    assert "preferred_min_throughput" in text or "preferred_max_latency" in text
    assert "ttft" in lower or "throughput" in lower
    assert "virtual_model_selection" in text
    assert "performance" in text
    assert "ordered" in lower
    # Do not claim marketplace / CSAM / Private Endpoints as daari features here.
    assert "does not claim" in lower or "not a clone" in lower or "not claim" in lower


def test_compare_index_mentions_live_scoring_row() -> None:
    text = INDEX.read_text(encoding="utf-8")
    assert "virtual_model_selection" in text or "Live provider" in text
    assert "compare-openrouter.md" in text
