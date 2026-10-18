"""Anthropic fast-mode rate-limit headers are documented (#1764)."""

from pathlib import Path


PAGE = Path("docs/developer/guides/operations/fast-mode-headers.md")
NAV = Path("mkdocs.yml")

HEADER_NAMES = (
    "anthropic-fast-input-tokens-limit",
    "anthropic-fast-input-tokens-remaining",
    "anthropic-fast-input-tokens-reset",
    "anthropic-fast-output-tokens-limit",
    "anthropic-fast-output-tokens-remaining",
    "anthropic-fast-output-tokens-reset",
)


def test_fast_mode_header_page_names_allowlist_and_anthropic_l6():
    text = PAGE.read_text(encoding="utf-8")
    for name in HEADER_NAMES:
        assert name in text
    lower = text.lower()
    assert "anthropic l6" in lower
    assert "omitted" in lower
    assert "no other upstream" in lower or "other upstream headers are not copied" in lower
    nav = NAV.read_text(encoding="utf-8")
    assert "developer/guides/operations/fast-mode-headers.md" in nav
