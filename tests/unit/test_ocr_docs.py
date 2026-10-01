"""clients-and-gateways.md pin for POST /v1/ocr modality (#1274)."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOC = ROOT / "docs/developer/concepts/clients-and-gateways.md"


def test_clients_and_gateways_pins_ocr_modality() -> None:
    text = DOC.read_text(encoding="utf-8")
    assert "POST /v1/ocr" in text
    assert "document" in text
    assert "ocr.base_url" in text or "local" in text.lower()
    assert "vision" in text.lower() or "L6" in text
