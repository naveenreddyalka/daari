"""Doctor tip when mcp_policy.require_key_access_defined (#1352)."""

from __future__ import annotations

from pathlib import Path

from daari.setup.doctor import _check_mcp_require_key_access, run_doctor

DOCTOR_HEALTH = Path("docs/developer/guides/operations/doctor-health.md")


def test_tip_when_require_key_access_defined(settings):
    settings.integrations.mcp_policy.require_key_access_defined = True
    row = _check_mcp_require_key_access(settings)
    assert row is not None
    assert row.name == "mcp_require_key_access"
    assert row.optional is True
    assert row.ok is True
    detail = row.detail.lower()
    assert "require_key_access_defined" in detail
    assert "metadata.mcp" in detail or "mcp grant" in detail


def test_tip_absent_when_flag_off(settings):
    settings.integrations.mcp_policy.require_key_access_defined = False
    assert _check_mcp_require_key_access(settings) is None
    rows = run_doctor(settings, httpx_client=None)
    assert not any(r.name == "mcp_require_key_access" for r in rows)


def test_doctor_health_docs_mention_require_key_access_tip():
    text = DOCTOR_HEALTH.read_text(encoding="utf-8")
    assert "mcp_require_key_access" in text
    row = next(
        line
        for line in text.splitlines()
        if line.startswith("| doctor `mcp_require_key_access`")
    )
    assert "require_key_access_defined" in row
