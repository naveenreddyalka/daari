"""mcp.md pin for Mcp-Method/Name HEADER_MISMATCH honesty (#1255)."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MCP = ROOT / "docs/developer/guides/clients/mcp.md"


def test_mcp_guide_pins_header_mismatch() -> None:
    text = MCP.read_text(encoding="utf-8")
    assert "Mcp-Method" in text
    assert "Mcp-Name" in text
    assert "HEADER_MISMATCH" in text
    assert "-32023" in text
