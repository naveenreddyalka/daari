"""GTM-1: public copy must not claim OSI open source under PolyForm NC."""

from __future__ import annotations

from pathlib import Path

import tomllib

ROOT = Path(__file__).resolve().parents[2]

# Claims that the *product* is OSS. Relicensing language ("open-source licenses")
# in CONTRIBUTING is allowed and is not in this list.
UNQUALIFIED_OSS_CLAIMS = (
    "open-source local execution",
    "open-source local-first",
    "open-source **local",
    "is an open-source",
    "is an **open-source",
    "open-source local cost",
    "open-source **local-first",
    "daari is an open-source",
)

PUBLIC_COPY = (
    ROOT / "README.md",
    ROOT / "CONTRIBUTING.md",
    ROOT / "docs" / "developer" / "concepts" / "what-is-daari.md",
    ROOT / "docs" / "developer" / "concepts" / "glossary.md",
)


def test_public_copy_does_not_claim_unqualified_open_source():
    hits: list[str] = []
    for path in PUBLIC_COPY:
        text = path.read_text(encoding="utf-8").lower()
        for claim in UNQUALIFIED_OSS_CLAIMS:
            if claim in text:
                hits.append(f"{path.relative_to(ROOT)}: {claim!r}")
    assert hits == []


def test_readme_names_polyform_and_shows_l0_path():
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    lower = text.lower()
    assert "polyform" in lower
    assert "noncommercial" in lower
    assert "pip install daari" in text
    assert "docker compose up" in text
    assert '"tier": "L0"' in text
    assert "https://naveenreddyalka.github.io/daari/" in text


def test_pyproject_points_at_docs_site():
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    urls = data["project"]["urls"]
    docs = urls.get("Documentation") or urls.get("Docs")
    assert docs == "https://naveenreddyalka.github.io/daari/"
    assert data["project"]["description"]
