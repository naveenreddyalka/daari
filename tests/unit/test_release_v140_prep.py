"""Release prep for v1.4.0 (issue #334) — agent prepares; human tags.

Pins the artifacts that make ``git tag`` / ``gh release create`` a one-command
action. Does not create tags or publish.
"""

from __future__ import annotations

import re
from pathlib import Path

import daari

REPO_ROOT = Path(__file__).resolve().parents[2]
VERSION = "1.4.0"


def _pyproject_version() -> str:
    text = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r'^version\s*=\s*"([^"]+)"', text, re.MULTILINE)
    assert match, "pyproject.toml must declare version"
    return match.group(1)


def test_package_version_is_140():
    assert _pyproject_version() == VERSION
    assert daari.__version__ == VERSION


def test_readme_status_points_at_140():
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    assert f"v{VERSION}" in readme
    assert f"RELEASE-v{VERSION}.md" in readme


def test_release_notes_exist_and_lead_with_license_and_supply_chain():
    notes = (REPO_ROOT / f"docs/RELEASE-v{VERSION}.md").read_text(encoding="utf-8")
    assert notes.index("Apache 2.0") < notes.index("## Highlights")
    assert "cosign" in notes.lower()
    assert "SBOM" in notes or "sbom" in notes.lower()
    assert "Human steps remaining" in notes or "human steps" in notes.lower()
    assert "git tag" in notes
    assert "gh release create" in notes
    # Fleet upgrade guide from #316
    assert "developer/guides/operations/upgrade.md" in notes
    assert "## Upgrade notes" in notes
    # Highlight PRs called out in the issue must appear or be folded
    for pr in ("#293", "#311", "#307", "#314", "#303", "#316"):
        assert pr in notes, f"release notes must mention {pr}"


def test_releasing_checklist_covers_cosign_and_sbom():
    releasing = (REPO_ROOT / "docs/RELEASING.md").read_text(encoding="utf-8")
    assert "cosign" in releasing.lower()
    assert "SBOM" in releasing or "sbom" in releasing.lower()
    assert "provenance" in releasing.lower()
    assert "docker.yml" in releasing


def test_changelog_has_140_section():
    changelog = (REPO_ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    assert f"## [{VERSION}]" in changelog
    assert "docs/RELEASE-v1.4.0.md" in changelog
