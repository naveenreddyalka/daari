"""auth-and-keys guide documents server.header_policy (#1194)."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_auth_guide_documents_header_policy() -> None:
    text = (
        ROOT / "docs/developer/guides/configuration/auth-and-keys.md"
    ).read_text(encoding="utf-8")
    assert "header_policy" in text
    assert "header_policy_error" in text
    assert "server.header_policy" in text or "header_policy.enabled" in text
    assert "server.headerPolicy" in text or "capacity-helm" in text
