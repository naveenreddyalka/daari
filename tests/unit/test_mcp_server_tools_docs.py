"""Hermetic pin for per-key MCP tool-name allowlists in docs (#1288)."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "docs/developer/reference/config.md"
MCP = ROOT / "docs/developer/guides/clients/mcp.md"


def test_config_md_pins_server_tools() -> None:
    text = CONFIG.read_text(encoding="utf-8")
    assert "integrations.mcp_policy.server_tools" in text
    row = next(line for line in text.splitlines() if "mcp_policy.server_tools" in line)
    lower = row.lower()
    assert "server" in lower and "tool" in lower
    assert "empty" in lower or "fail" in lower


def test_mcp_guide_pins_server_tools_section() -> None:
    text = MCP.read_text(encoding="utf-8")
    assert "server_tools" in text
    section = text.split("### Per-server tool allowlists", 1)[1].split("\n### ", 1)[0]
    lower = section.lower()
    assert "--mcp-server-tools" in section
    assert "intersection" in lower
    assert "fail" in lower and "closed" in lower
    assert "tools/list" in lower and "tools/call" in lower
    assert "mcp_servers" in section or "responses" in lower
    assert "-32003" in section or "mcp_tool_denied" in section
