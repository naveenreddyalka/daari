"""GTM-6: Discussions templates exist and stay license-honest."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GTM = ROOT / "docs" / "gtm" / "discussions"

TEMPLATES = (
    GTM / "README.md",
    GTM / "welcome.md",
    GTM / "show-report.md",
    GTM / "setup-help.md",
)

BANNED = (
    "open-source local execution",
    "is an open-source",
    "open source local",
)


def test_discussion_templates_exist():
    for path in TEMPLATES:
        assert path.is_file(), path.name
        assert path.stat().st_size > 200


def test_templates_are_license_honest_and_linkable():
    docs = "https://naveenreddyalka.github.io/daari/"
    repo = "https://github.com/naveenreddyalka/daari"
    for path in TEMPLATES:
        text = path.read_text(encoding="utf-8")
        lower = text.lower()
        for claim in BANNED:
            assert claim not in lower, f"{path.name}: {claim}"
        assert "apache" in lower
        assert docs in text or repo in text


def test_readme_and_contributing_link_discussions():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    contributing = (ROOT / "CONTRIBUTING.md").read_text(encoding="utf-8")
    assert "github.com/naveenreddyalka/daari/discussions" in readme
    assert "github.com/naveenreddyalka/daari/discussions" in contributing
    assert "docs/gtm/discussions" in readme or "gtm/discussions" in readme


def test_publish_instructions_use_gh():
    text = (GTM / "README.md").read_text(encoding="utf-8")
    assert "gh discussion create" in text
    assert "Do not spam" in text or "do not spam" in text.lower()
    assert "238" in text
