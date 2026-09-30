"""Claude Code guide pins Effort (output_config) behavior (#1246)."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOC = ROOT / "docs/developer/guides/clients/claude-code.md"


def test_claude_code_guide_pins_output_config_effort() -> None:
    text = DOC.read_text(encoding="utf-8")
    assert "## Effort (`output_config`)" in text
    assert "output_config" in text
    assert "effort" in text
    assert "xhigh" in text and "max" in text
    assert "high" in text
    assert "→" in text or "->" in text
    assert "anthropic-beta" in text
    assert "effort-2025-11-24" in text
