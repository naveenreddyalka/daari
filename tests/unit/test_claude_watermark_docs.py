"""Claude Code guide pins the text-watermark sampling caveat (#2340)."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOC = ROOT / "docs/developer/guides/clients/claude-code.md"
TRACKING = ROOT / "docs/TRACKING.md"

_MODELS = (
    "Opus 4.6",
    "Opus 4.5",
    "Opus 3",
    "Sonnet 4.6",
    "Sonnet 4.5",
    "Haiku 4.5",
)


def test_claude_code_guide_pins_text_watermark_sampling() -> None:
    text = DOC.read_text(encoding="utf-8")
    assert "## Text watermark (sampling)" in text
    for model in _MODELS:
        assert model in text
    assert "temperature" in text
    assert "top_p" in text
    assert "top_k" in text
    lowered = text.lower()
    assert "detectable mark" in lowered
    assert "does not inject" in lowered
    assert "client legs" in lowered
    assert "passed through" in lowered
    assert "may drop" in lowered
    assert "does not ship watermark detection" in lowered
    assert "compliance api" in lowered
    assert "anthropic-side" in lowered
    assert (
        "https://platform.claude.com/docs/en/build-with-claude/text-watermark" in text
    )


def test_tracking_pins_claude_watermark_caveat() -> None:
    text = TRACKING.read_text(encoding="utf-8")
    assert "<!-- tracking:#2340 -->" in text
    assert (
        "https://github.com/naveenreddyalka/daari/issues/2340" in text
    )
    how = text.find("\n## How to update\n")
    section = text.rfind("<!-- tracking:#2340 -->", 0, how)
    assert section != -1
