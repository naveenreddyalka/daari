"""http-api.md pin for GET /v1/mcp/registry.json row (#1285)."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HTTP_API = ROOT / "docs/developer/reference/http-api.md"


def test_http_api_pins_mcp_registry_row() -> None:
    text = HTTP_API.read_text(encoding="utf-8")
    assert "| `GET` | `/v1/mcp/registry.json`" in text
