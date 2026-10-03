"""auth-and-keys.md pin for watchdog sandbox master-key hatch (#1341)."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
AUTH = ROOT / "docs/developer/guides/configuration/auth-and-keys.md"


def test_auth_docs_pin_watchdog_sandbox_hatch_and_install() -> None:
    text = AUTH.read_text(encoding="utf-8")
    assert "DAARI_SERVER__DANGEROUSLY_PERMIT_WEAK_OR_UNSET_API_KEY" in text
    assert "autodev-local.sh --install" in text
    assert "dangerously_permit_weak_or_unset_api_key" in text
