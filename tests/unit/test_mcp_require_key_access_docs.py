"""Hermetic pin for require_key_access_defined in mcp and config (#1360)."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "docs/developer/reference/config.md"
MCP = ROOT / "docs/developer/guides/clients/mcp.md"


def test_config_md_pins_require_key_access_defined() -> None:
    text = CONFIG.read_text(encoding="utf-8")
    assert "integrations.mcp_policy.require_key_access_defined" in text
    lower = text.lower()
    assert "metadata.mcp" in lower or "grant" in lower
    assert "tools/list" in lower or "tools/call" in lower
    assert "deny" in lower


def test_mcp_guide_pins_require_key_access_defined() -> None:
    text = MCP.read_text(encoding="utf-8")
    assert "require_key_access_defined" in text
    lower = text.lower()
    assert "fail-closed" in lower or "fail closed" in lower
    assert "grant" in lower
    assert "master" in lower and "unchanged" in lower
