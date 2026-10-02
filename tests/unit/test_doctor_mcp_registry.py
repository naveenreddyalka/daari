"""Doctor tip when mcp_registry.enabled advertises discovery (#1287)."""

from __future__ import annotations

from daari.setup.doctor import _check_mcp_registry, run_doctor


def test_tip_when_registry_enabled(settings):
    settings.integrations.mcp_registry.enabled = True
    row = _check_mcp_registry(settings)
    assert row is not None
    assert row.name == "mcp_registry"
    assert row.optional is True
    assert "/v1/mcp/registry.json" in row.detail
    assert "/mcp" in row.detail
    assert "auth" in row.detail.lower() or "API-key" in row.detail or "allowlist" in row.detail


def test_tip_absent_when_registry_disabled(settings):
    settings.integrations.mcp_registry.enabled = False
    assert _check_mcp_registry(settings) is None
    rows = run_doctor(settings, httpx_client=None)
    assert not any(r.name == "mcp_registry" for r in rows)


def test_doctor_health_docs_mention_mcp_registry_tip():
    from pathlib import Path

    text = Path("docs/developer/guides/operations/doctor-health.md").read_text()
    assert "mcp_registry" in text
    assert "/v1/mcp/registry.json" in text
