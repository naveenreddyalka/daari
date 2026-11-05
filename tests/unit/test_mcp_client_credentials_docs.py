"""mcp.md / config.md pin client-credentials upstream auth via secret://oauth (#2088)."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MCP = ROOT / "docs/developer/guides/clients/mcp.md"
CONFIG = ROOT / "docs/developer/reference/config.md"


def test_mcp_guide_documents_client_credentials_upstream_auth() -> None:
    text = MCP.read_text(encoding="utf-8")
    assert "Machine-to-machine upstream auth (client credentials)" in text
    assert "secret://oauth" in text
    assert "scope=" in text
    assert "auto-refresh" in text.lower() or "near expiry" in text.lower() or "refresh" in text.lower()
    # Nested client_secret must be another secret:// ref (never inline).
    assert "secret://keychain" in text or "secret://env-file" in text or "secret://exec" in text
    # Cross-link OBO (caller identity) vs fixed service identity.
    assert "oauth2_token_exchange" in text
    assert "fixed service identity" in text.lower() or "service identity" in text.lower()


def test_config_md_mcp_servers_token_accepts_oauth_secret_refs() -> None:
    text = CONFIG.read_text(encoding="utf-8")
    row_start = text.find("| `integrations.mcp_servers`")
    assert row_start >= 0
    row = text[row_start : text.find("\n", row_start)]
    assert "secret://" in row
    assert "oauth" in row.lower()
