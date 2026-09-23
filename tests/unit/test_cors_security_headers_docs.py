"""config.md documents server.cors_origins and security_headers (#966)."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_config_documents_cors_and_security_headers() -> None:
    config = (ROOT / "docs/developer/reference/config.md").read_text(encoding="utf-8")
    assert "server.cors_origins" in config
    assert "server.security_headers" in config
