"""org-cache + doctor-health document scoped_cache_fleet (#899, #908)."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ORG = ROOT / "docs/developer/guides/features/org-cache.md"
DOCTOR = ROOT / "docs/developer/guides/operations/doctor-health.md"


def test_org_cache_documents_scoped_cache_fleet() -> None:
    text = ORG.read_text(encoding="utf-8")
    assert "scoped_cache_fleet" in text
    assert "redis" in text.lower()
    assert "cache_scope" in text
    assert "doctor-health" in text or "doctor" in text.lower()


def test_doctor_health_lists_scoped_cache_fleet() -> None:
    text = DOCTOR.read_text(encoding="utf-8")
    assert "scoped_cache_fleet" in text


def test_doctor_health_scoped_cache_fleet_row_mentions_backend_and_scope() -> None:
    text = DOCTOR.read_text(encoding="utf-8")
    row = next(
        line
        for line in text.splitlines()
        if line.startswith("|") and "scoped_cache_fleet" in line
    )
    assert "cache.backend" in row or "redis" in row.lower()
    assert "cache_scope" in row
