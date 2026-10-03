"""Hermetic pin for decision_classifier config rows (#1315)."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "docs/developer/reference/config.md"


def test_config_md_pins_decision_classifier_rows() -> None:
    text = CONFIG.read_text(encoding="utf-8")
    assert "routing.decision_classifier.enabled" in text
    assert "routing.decision_classifier.model" in text
    assert "routing.decision_classifier.timeout_seconds" in text
    assert "fall back" in text or "fallback" in text.lower()
    assert "timeout" in text
