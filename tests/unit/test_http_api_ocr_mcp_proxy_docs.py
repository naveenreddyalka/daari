"""http-api.md pin for OCR and /mcp/proxy rows (#1278)."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HTTP_API = ROOT / "docs/developer/reference/http-api.md"


def test_http_api_pins_ocr_and_mcp_proxy_rows() -> None:
    text = HTTP_API.read_text(encoding="utf-8")
    assert "POST" in text and "/v1/ocr" in text
    assert "POST" in text and "/mcp/proxy" in text
    assert "| `POST` | `/v1/ocr`" in text
    assert "| `POST` | `/mcp/proxy`" in text
