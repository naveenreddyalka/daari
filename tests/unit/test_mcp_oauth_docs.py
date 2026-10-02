"""mcp.md / config.md pin RFC 9728 oauth-protected-resource discovery (#1262, #1293)."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MCP = ROOT / "docs/developer/guides/clients/mcp.md"
CONFIG = ROOT / "docs/developer/reference/config.md"


def test_mcp_guide_pins_oauth_protected_resource() -> None:
    text = MCP.read_text(encoding="utf-8")
    assert "protected_resource" in text
    assert "oauth-protected-resource" in text
    assert "WWW-Authenticate" in text


def test_mcp_guide_pins_local_as_token_mint() -> None:
    text = MCP.read_text(encoding="utf-8")
    assert "local_as" in text
    assert "/oauth/token" in text
    assert "client_credentials" in text


def test_config_md_lists_mcp_oauth() -> None:
    text = CONFIG.read_text(encoding="utf-8")
    assert "integrations.mcp_oauth.protected_resource" in text
    assert "integrations.mcp_oauth.local_as" in text
    assert "integrations.mcp_oauth.token_ttl_seconds" in text
