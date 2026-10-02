"""mcp.md / config.md pin aggregate egress catalog (#1294)."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MCP = ROOT / "docs/developer/guides/clients/mcp.md"
CONFIG = ROOT / "docs/developer/reference/config.md"


def test_mcp_guide_pins_aggregate_egress() -> None:
    text = MCP.read_text(encoding="utf-8")
    assert "mcp_aggregate_egress" in text
    assert "{server_id}__{tool}" in text or "server_id}__{tool" in text
    assert "mcp_aggregate_egress_list_failed" in text


def test_config_md_lists_aggregate_egress() -> None:
    text = CONFIG.read_text(encoding="utf-8")
    assert "integrations.mcp_aggregate_egress.enabled" in text
