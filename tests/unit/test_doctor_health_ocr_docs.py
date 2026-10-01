"""Doctor-health documents OCR unset tip (#1276)."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOCTOR_HEALTH = ROOT / "docs/developer/guides/operations/doctor-health.md"


def test_doctor_health_ocr_row() -> None:
    text = DOCTOR_HEALTH.read_text(encoding="utf-8")
    row = next(line for line in text.splitlines() if line.startswith("| doctor `ocr`"))
    assert "ocr.base_url" in row
    assert "ocr.vision_model" in row
    assert "/v1/ocr" in row or "clients-and-gateways" in row
