"""Doctor tip when mcp_oauth.local_as mints tokens (#1312)."""

from __future__ import annotations

from daari.setup.doctor import _check_mcp_oauth_local_as, run_doctor


def test_tip_when_local_as_enabled(settings):
    settings.integrations.mcp_oauth.local_as = True
    row = _check_mcp_oauth_local_as(settings)
    assert row is not None
    assert row.name == "mcp_oauth_local_as"
    assert row.optional is True
    assert row.ok is True
    detail = row.detail.lower()
    assert "/oauth/token" in detail or "token" in detail
    assert "/mcp" in detail
    assert "bearer" in detail or "auth" in detail


def test_tip_absent_when_local_as_disabled(settings):
    settings.integrations.mcp_oauth.local_as = False
    assert _check_mcp_oauth_local_as(settings) is None
    rows = run_doctor(settings, httpx_client=None)
    assert not any(r.name == "mcp_oauth_local_as" for r in rows)


def test_doctor_health_docs_mention_mcp_oauth_local_as_tip():
    from pathlib import Path

    text = Path("docs/developer/guides/operations/doctor-health.md").read_text()
    assert "mcp_oauth_local_as" in text or "local_as" in text
    assert "/oauth/token" in text or "token mint" in text.lower()
