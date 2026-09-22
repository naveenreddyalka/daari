"""Client guides mention Ollama /api/show thinking controls (#809)."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GUIDES = ROOT / "docs/developer/guides/clients"


def test_chatgpt_and_intellij_mention_show_thinking_controls() -> None:
    for name in ("chatgpt-desktop.md", "intellij.md"):
        text = (GUIDES / name).read_text(encoding="utf-8")
        assert "thinking" in text and "controls" in text
        assert "low" in text and "medium" in text and "high" in text
        assert "/api/show" in text
