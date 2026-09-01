"""GTM-3: launch plan and drafts exist and stay license-honest."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GTM = ROOT / "docs" / "gtm"

DRAFTS = (
    GTM / "launches" / "show-hn.md",
    GTM / "launches" / "localllama.md",
    GTM / "launches" / "cursor.md",
    GTM / "launches" / "product-hunt.md",
)

BANNED = (
    "open-source local execution",
    "is an open-source",
    "open source local",
)


def test_plan_and_drafts_exist():
    assert (GTM / "PLAN.md").is_file()
    for path in DRAFTS:
        assert path.is_file(), path.name
        assert path.stat().st_size > 200


def test_drafts_are_license_honest_and_linkable():
    docs = "https://naveenreddyalka.github.io/daari/"
    repo = "https://github.com/naveenreddyalka/daari"
    for path in DRAFTS:
        text = path.read_text(encoding="utf-8")
        lower = text.lower()
        for claim in BANNED:
            assert claim not in lower, f"{path.name}: {claim}"
        assert "apache" in lower
        assert docs in text
        assert repo in text


def test_tracking_has_gtm_section():
    text = (ROOT / "docs" / "TRACKING.md").read_text(encoding="utf-8")
    assert "## GTM" in text
    assert "docs/gtm/PLAN.md" in text
