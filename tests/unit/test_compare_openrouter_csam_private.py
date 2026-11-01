"""Hermetic pin: OpenRouter CSAM screening + Private Endpoints vs daari (#2038)."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
COMPARE = ROOT / "docs/developer/resources/compare-openrouter.md"
LANDSCAPE = ROOT / "docs/discovery/04-competitive-landscape.md"
INDEX = ROOT / "docs/developer/resources/compare.md"


def test_compare_openrouter_pins_private_endpoints_and_csam() -> None:
    text = COMPARE.read_text(encoding="utf-8")
    lower = text.lower()
    assert "private endpoint" in lower
    assert "csam" in lower
    assert "openrouter.ai/blog/announcements/csam-screening" in text
    assert "openrouter.ai/blog/announcements/private-endpoints" in text
    assert "zdr" in lower
    assert "local" in lower and ("tier" in lower or "on-device" in lower or "on-box" in lower)
    assert "guardrail" in lower or "on-box" in lower


def test_landscape_openrouter_row_notes_2026_delta() -> None:
    text = LANDSCAPE.read_text(encoding="utf-8")
    lower = text.lower()
    assert "openrouter" in lower
    assert "2026-10" in text or "late oct 2026" in lower or "october 2026" in lower
    assert "private endpoint" in lower or "csam" in lower


def test_compare_index_still_links_openrouter() -> None:
    text = INDEX.read_text(encoding="utf-8")
    assert "compare-openrouter.md" in text
    assert "OpenRouter" in text
