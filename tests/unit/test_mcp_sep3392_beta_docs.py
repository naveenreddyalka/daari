"""mcp.md pin for SEP-3392 Beta lifecycle on Skills and Tasks (#2039)."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MCP = ROOT / "docs/developer/guides/clients/mcp.md"


def test_mcp_guide_pins_sep3392_skills_beta_lifecycle() -> None:
    text = MCP.read_text(encoding="utf-8")
    assert "SEP-3392" in text
    assert "Beta" in text
    assert "SEP-2640" in text
    assert "https://modelcontextprotocol.io/extensions/skills/overview" in text
    assert "specification/beta" in text
    assert "specification/stable/" not in text


def test_mcp_guide_pins_tasks_beta_to_core() -> None:
    text = MCP.read_text(encoding="utf-8")
    tasks = text.split("## Tasks", 1)[1]
    assert "Beta" in tasks
    assert "Core" in tasks
    assert "breaking" in tasks.lower()
    assert "https://modelcontextprotocol.io/extensions/overview" in text
