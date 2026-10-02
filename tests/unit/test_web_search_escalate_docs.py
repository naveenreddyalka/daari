"""clients-and-gateways.md pin for web_search_options escalate (#1305)."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GUIDE = ROOT / "docs/developer/concepts/clients-and-gateways.md"


def test_clients_guide_pins_web_search_options_escalate() -> None:
    text = GUIDE.read_text(encoding="utf-8")
    assert "web_search_options" in text
    assert "L6" in text or "frontier" in text.lower()
    lowered = text.lower()
    assert "escalate" in lowered or "fail" in lowered or "4xx" in lowered or "501" in text
