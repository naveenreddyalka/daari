"""Doctor tip when observability.structured_json_logs is on (#1431)."""

from __future__ import annotations

from pathlib import Path

from daari.setup.doctor import _check_structured_json_logs, run_doctor

DOCTOR_HEALTH = Path("docs/developer/guides/operations/doctor-health.md")


def test_tip_when_structured_json_logs_enabled(settings):
    settings.observability.structured_json_logs = True
    row = _check_structured_json_logs(settings)
    assert row is not None
    assert row.name == "structured_json_logs"
    assert row.optional is True
    assert row.ok is True
    detail = row.detail.lower()
    assert "stdout" in detail
    assert "json" in detail


def test_tip_absent_when_structured_json_logs_disabled(settings):
    settings.observability.structured_json_logs = False
    assert _check_structured_json_logs(settings) is None
    rows = run_doctor(settings, httpx_client=None)
    assert not any(r.name == "structured_json_logs" for r in rows)


def test_doctor_health_docs_mention_structured_json_logs_tip():
    text = DOCTOR_HEALTH.read_text(encoding="utf-8")
    row = next(
        line
        for line in text.splitlines()
        if line.startswith("| doctor `structured_json_logs`")
    )
    assert "structured_json_logs" in row
    assert "stdout" in row.lower()
    assert "json" in row.lower()
