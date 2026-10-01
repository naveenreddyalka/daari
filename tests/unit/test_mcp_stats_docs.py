"""mcp.md pin for mcp_tool_calls / mcp_tasks stats cues (#1257)."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MCP = ROOT / "docs/developer/guides/clients/mcp.md"


def test_mcp_guide_pins_stats_mcp_tool_calls_and_tasks() -> None:
    text = MCP.read_text(encoding="utf-8")
    assert "/v1/daari/stats" in text
    assert "mcp_tool_calls" in text
    assert "mcp_tasks" in text
