"""auth-and-keys pins secrets.refresh_ttl_seconds runbook (#1248)."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
AUTH = ROOT / "docs/developer/guides/configuration/auth-and-keys.md"
CONFIG = ROOT / "docs/developer/reference/config.md"


def test_auth_guide_pins_secret_refresh_ttl_runbook() -> None:
    text = AUTH.read_text(encoding="utf-8")
    assert "### Refresh and rotation (#1204)" in text
    assert "secrets.refresh_ttl_seconds" in text
    assert "**300**" in text
    assert "DAARI_SECRETS__REFRESH_TTL_SECONDS=0" in text
    assert "boot-only" in text
    assert "mtime" in text
    assert "secret_refs" in text
    assert "exec" in text and "keychain" in text


def test_config_md_lists_secrets_refresh_ttl_seconds() -> None:
    text = CONFIG.read_text(encoding="utf-8")
    assert "secrets.refresh_ttl_seconds" in text
    assert "300" in text
    assert "DAARI_SECRETS__REFRESH_TTL_SECONDS" in text
