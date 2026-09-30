"""mcp.md / config.md pin Responses server_side_responses (#1254)."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MCP = ROOT / "docs/developer/guides/clients/mcp.md"
CONFIG = ROOT / "docs/developer/reference/config.md"


def test_mcp_guide_pins_server_side_responses() -> None:
    text = MCP.read_text(encoding="utf-8")
    assert "server_side_responses" in text
    assert "type: mcp" in text
    assert "server_label" in text
    assert "400" in text


def test_config_md_lists_server_side_responses() -> None:
    text = CONFIG.read_text(encoding="utf-8")
    assert "integrations.mcp_egress.server_side_responses" in text
