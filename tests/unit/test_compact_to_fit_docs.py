"""Hermetic pin for compact_to_fit in config and routing-tiers (#1350)."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "docs/developer/reference/config.md"
ROUTING = ROOT / "docs/developer/concepts/routing-tiers.md"


def test_config_md_pins_compact_to_fit_keys() -> None:
    text = CONFIG.read_text(encoding="utf-8")
    assert "routing.compact_to_fit.enabled" in text
    assert "routing.compact_to_fit.max_messages" in text
    assert "routing.compact_to_fit.max_tokens" in text
    lower = text.lower()
    assert "fail closed" in lower or "fail-closed" in lower
    assert "tool-call" in lower or "tool payload" in lower or "tool-call payloads" in lower


def test_routing_tiers_pins_compact_to_fit() -> None:
    text = ROUTING.read_text(encoding="utf-8")
    lower = text.lower()
    assert "compact_to_fit" in text or "compact-to-fit" in lower
    assert "compact" in lower and ("l6" in lower or "frontier" in lower)
    assert "fail closed" in lower or "fail-closed" in lower
    assert "tool-call" in lower or "tool payload" in lower
    assert "tokens_before" in text
    assert "tokens_after" in text
    assert "compact_to_fit_tokens_dropped" in text or "tokens_dropped" in text
