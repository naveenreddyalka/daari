"""Doctor-health documents images_generations probe (#1092)."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOCTOR_HEALTH = ROOT / "docs/developer/guides/operations/doctor-health.md"


def test_doctor_health_images_generations_row() -> None:
    text = DOCTOR_HEALTH.read_text(encoding="utf-8")
    row = next(
        line for line in text.splitlines() if line.startswith("| doctor `images_generations`")
    )
    assert "frontier.enabled" in row
    assert "/v1/images/generations" in row
