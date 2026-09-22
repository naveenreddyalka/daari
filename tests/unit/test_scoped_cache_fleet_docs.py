"""Doctor-health table documents scoped_cache_fleet tenancy (#908)."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOCTOR_HEALTH = ROOT / "docs/developer/guides/operations/doctor-health.md"


def test_doctor_health_scoped_cache_fleet_row_mentions_backend_and_scope() -> None:
    text = DOCTOR_HEALTH.read_text(encoding="utf-8")
    row = next(
        line
        for line in text.splitlines()
        if line.startswith("|") and "scoped_cache_fleet" in line
    )
    assert "cache.backend" in row or "redis" in row.lower()
    assert "cache_scope" in row
