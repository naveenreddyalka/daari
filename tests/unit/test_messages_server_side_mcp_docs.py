"""mcp.md / config.md pin Messages server_side_messages (#1261)."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MCP = ROOT / "docs/developer/guides/clients/mcp.md"
CONFIG = ROOT / "docs/developer/reference/config.md"


def test_mcp_guide_pins_server_side_messages() -> None:
    text = MCP.read_text(encoding="utf-8")
    assert "server_side_messages" in text
    assert "mcp_toolset" in text
    assert "mcp_server_name" in text
    assert "400" in text


def test_config_md_lists_server_side_messages() -> None:
    text = CONFIG.read_text(encoding="utf-8")
    assert "integrations.mcp_egress.server_side_messages" in text
