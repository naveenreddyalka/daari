"""Public copy matches Apache 2.0 (ADR-0016 / #227)."""

from __future__ import annotations

from pathlib import Path

import tomllib

ROOT = Path(__file__).resolve().parents[2]

PUBLIC_COPY = (
    ROOT / "README.md",
    ROOT / "CONTRIBUTING.md",
    ROOT / "docs" / "developer" / "concepts" / "what-is-daari.md",
)


def test_license_file_is_apache_2():
    text = (ROOT / "LICENSE").read_text(encoding="utf-8")
    assert "Apache License" in text
    assert "Version 2.0" in text
    assert "PolyForm" not in text


def test_readme_names_apache_and_shows_l0_path():
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    lower = text.lower()
    assert "apache 2.0" in lower or "apache license 2.0" in lower
    assert "polyform" not in lower
    assert "pip install daari" in text
    assert "docker compose up" in text
    assert '"tier": "L0"' in text
    assert "https://naveenreddyalka.github.io/daari/" in text


def test_public_copy_does_not_claim_current_license_is_polyform():
    hits: list[str] = []
    for path in PUBLIC_COPY:
        lower = path.read_text(encoding="utf-8").lower()
        if "polyform" in lower or "noncommercial" in lower:
            hits.append(str(path.relative_to(ROOT)))
    assert hits == []


def test_pyproject_is_apache_and_points_at_docs_site():
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    urls = data["project"]["urls"]
    docs = urls.get("Documentation") or urls.get("Docs")
    assert docs == "https://naveenreddyalka.github.io/daari/"
    assert data["project"]["description"]
    assert data["project"]["license"]["text"] == "Apache-2.0"
    assert "License :: OSI Approved :: Apache Software License" in data["project"][
        "classifiers"
    ]
