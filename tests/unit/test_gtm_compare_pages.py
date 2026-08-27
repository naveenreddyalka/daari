"""GTM-4: launch-facing comparison pages stay license-honest and linked."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PAGES = (
    ROOT / "docs" / "developer" / "resources" / "compare-litellm.md",
    ROOT / "docs" / "developer" / "resources" / "compare-ollama.md",
    ROOT / "docs" / "developer" / "resources" / "compare-openrouter.md",
)
BANNED = ("open-source local execution", "is an open-source", "open source local")


def test_compare_pages_exist_and_are_honest():
    nav = (ROOT / "mkdocs.yml").read_text(encoding="utf-8")
    index = (ROOT / "docs" / "developer" / "resources" / "compare.md").read_text(
        encoding="utf-8"
    )
    for path in PAGES:
        text = path.read_text(encoding="utf-8")
        lower = text.lower()
        assert path.stat().st_size > 400, path.name
        assert "polyform" in lower or "noncommercial" in lower
        for claim in BANNED:
            assert claim not in lower, f"{path.name}: {claim}"
        assert path.name in nav
        assert path.name in index
