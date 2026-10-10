"""auth-and-keys.md lists decisions in rate_families (#1501)."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
AUTH = ROOT / "docs/developer/guides/configuration/auth-and-keys.md"


def test_auth_and_keys_lists_decisions_rate_family() -> None:
    text = AUTH.read_text(encoding="utf-8")
    assert "`decisions`" in text
    assert "POST /v1/decisions" in text
    assert "--rate-family decisions:" in text
