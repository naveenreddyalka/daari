"""mcp.md pin for OpenAPI /mcp/proxy cues (#1275)."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MCP = ROOT / "docs/developer/guides/clients/mcp.md"


def test_mcp_guide_pins_openapi_proxy_cues() -> None:
    text = MCP.read_text(encoding="utf-8")
    assert "/mcp/proxy" in text
    assert "mcp_openapi_proxy" in text
    assert "tools/list" in text
    assert "allow_private_networks" in text
    assert "SSRF" in text
