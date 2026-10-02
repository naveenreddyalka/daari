"""config.md pin for mcp_openapi_proxy + mcp_registry rows (#1286)."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "docs/developer/reference/config.md"


def test_config_pins_mcp_openapi_proxy_and_registry_rows() -> None:
    text = CONFIG.read_text(encoding="utf-8")
    assert "integrations.mcp_openapi_proxy.enabled" in text
    assert "integrations.mcp_registry.enabled" in text
    assert "/mcp/proxy" in text
    assert "/v1/mcp/registry.json" in text
