"""config.md documents server body/TLS and auth throttle knobs (#998)."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_config_documents_body_tls_and_auth() -> None:
    config = (ROOT / "docs/developer/reference/config.md").read_text(encoding="utf-8")
    for key in (
        "server.max_body_bytes",
        "server.tls.cert_file",
        "server.tls.key_file",
        "server.tls.client_ca",
        "auth.throttle_enabled",
        "auth.max_failures",
        "auth.window_seconds",
        "auth.exempt_loopback",
    ):
        assert key in config, key
    # Hand-written rpd footnote must survive (#733 / #998).
    assert "rpd" in config
    assert "auth-and-keys.md" in config
