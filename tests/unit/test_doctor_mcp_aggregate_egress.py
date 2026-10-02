"""Doctor tip when mcp_aggregate_egress.enabled merges catalog (#1306)."""

from __future__ import annotations

from daari.setup.doctor import _check_mcp_aggregate_egress, run_doctor


def test_tip_when_aggregate_egress_enabled(settings):
    settings.integrations.mcp_aggregate_egress.enabled = True
    row = _check_mcp_aggregate_egress(settings)
    assert row is not None
    assert row.name == "mcp_aggregate_egress"
    assert row.optional is True
    assert row.ok is True
    detail = row.detail.lower()
    assert "/mcp" in detail
    assert "tools/list" in detail or "aggregate" in detail
    assert "policy" in detail or "ssrf" in detail


def test_tip_absent_when_aggregate_egress_disabled(settings):
    settings.integrations.mcp_aggregate_egress.enabled = False
    assert _check_mcp_aggregate_egress(settings) is None
    rows = run_doctor(settings, httpx_client=None)
    assert not any(r.name == "mcp_aggregate_egress" for r in rows)


def test_doctor_health_docs_mention_mcp_aggregate_egress_tip():
    from pathlib import Path

    text = Path("docs/developer/guides/operations/doctor-health.md").read_text()
    assert "mcp_aggregate_egress" in text
    assert "/mcp" in text
