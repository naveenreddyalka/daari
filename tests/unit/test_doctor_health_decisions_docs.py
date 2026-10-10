"""Doctor-health documents decisions tip (#1501)."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOCTOR_HEALTH = ROOT / "docs/developer/guides/operations/doctor-health.md"


def test_doctor_health_decisions_row() -> None:
    text = DOCTOR_HEALTH.read_text(encoding="utf-8")
    row = next(line for line in text.splitlines() if line.startswith("| doctor `decisions`"))
    assert "/v1/decisions" in row or "gpt-6-luna" in row
    assert "systemone" in row
