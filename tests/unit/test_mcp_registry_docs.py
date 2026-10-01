"""mcp.md pin for MCP registry.json cues (#1284)."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MCP = ROOT / "docs/developer/guides/clients/mcp.md"


def test_mcp_guide_pins_registry_json_cues() -> None:
    text = MCP.read_text(encoding="utf-8")
    assert "mcp_registry" in text
    assert "/v1/mcp/registry.json" in text
    assert "mcp_servers" in text
