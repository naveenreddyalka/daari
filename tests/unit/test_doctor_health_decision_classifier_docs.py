"""Doctor-health documents decision_classifier tip (#1323)."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOCTOR_HEALTH = ROOT / "docs/developer/guides/operations/doctor-health.md"


def test_doctor_health_decision_classifier_row() -> None:
    text = DOCTOR_HEALTH.read_text(encoding="utf-8")
    row = next(
        line
        for line in text.splitlines()
        if line.startswith("| doctor `decision_classifier`")
    )
    assert "decision_classifier.enabled" in row
    assert "systemone" in row or "difficulty hop" in row
