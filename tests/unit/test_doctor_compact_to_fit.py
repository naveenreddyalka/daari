"""Doctor tip when routing.compact_to_fit.enabled (#1349)."""

from __future__ import annotations

from pathlib import Path

from daari.setup.doctor import _check_compact_to_fit, run_doctor

DOCTOR_HEALTH = Path("docs/developer/guides/operations/doctor-health.md")


def test_tip_when_compact_to_fit_enabled(settings):
    settings.routing.compact_to_fit.enabled = True
    row = _check_compact_to_fit(settings)
    assert row is not None
    assert row.name == "compact_to_fit"
    assert row.optional is True
    assert row.ok is True
    detail = row.detail.lower()
    assert "l6" in detail or "frontier" in detail
    assert "tool" in detail
    assert "fail" in detail or "oversiz" in detail


def test_tip_absent_when_compact_to_fit_disabled(settings):
    settings.routing.compact_to_fit.enabled = False
    assert _check_compact_to_fit(settings) is None
    rows = run_doctor(settings, httpx_client=None)
    assert not any(r.name == "compact_to_fit" for r in rows)


def test_doctor_health_docs_mention_compact_to_fit_tip():
    text = DOCTOR_HEALTH.read_text(encoding="utf-8")
    assert "compact_to_fit" in text
    row = next(
        line
        for line in text.splitlines()
        if line.startswith("| doctor `compact_to_fit`")
    )
    assert "compact_to_fit.enabled" in row
    assert "L6" in row or "frontier" in row.lower()
