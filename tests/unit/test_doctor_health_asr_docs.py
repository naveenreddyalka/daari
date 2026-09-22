"""Doctor-health ASR row names frontier fallback (#917)."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOCTOR_HEALTH = ROOT / "docs/developer/guides/operations/doctor-health.md"


def test_doctor_health_asr_row_names_base_url_and_frontier_fallback() -> None:
    text = DOCTOR_HEALTH.read_text(encoding="utf-8")
    row = next(line for line in text.splitlines() if line.startswith("| doctor `asr`"))
    assert "asr.base_url" in row
    assert "frontier_fallback" in row
