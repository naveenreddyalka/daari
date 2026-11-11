"""Hermetic pin: OpenRouter Auto / Auto Code local-first positioning (#2171)."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
COMPARE = ROOT / "docs/developer/resources/compare-openrouter.md"


def test_compare_openrouter_pins_auto_and_auto_code() -> None:
    text = COMPARE.read_text(encoding="utf-8")
    lower = text.lower()
    assert "openrouter/auto" in text
    assert "auto-code" in lower or "openrouter/auto-code" in text
    assert "openrouter.ai/blog/announcements/auto-and-auto-code-routers" in text
    assert "2026-11-06" in text or "11-06" in text or "6 nov" in lower
    assert "does **not** clone" in lower or "does not clone" in lower
    assert "virtual_model" in text or "virtual-model" in lower
    assert "signal_overrides" in text
    assert "latency" in lower and "slo" in lower
    # Hosted marketplace stays optional L6, not the default path.
    assert "l6" in lower
    assert "local-first" in lower or "on-box" in lower or "on-device" in lower
