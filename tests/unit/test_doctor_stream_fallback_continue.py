"""Doctor tip when routing.stream_fallback_continue is on (#2305)."""

from __future__ import annotations

from daari.setup.doctor import _check_stream_fallback_continue, run_doctor


def test_tip_when_stream_fallback_continue_enabled(settings):
    settings.routing.stream_fallback_continue = True
    row = _check_stream_fallback_continue(settings)
    assert row is not None
    assert row.name == "stream_fallback_continue"
    assert row.optional is True
    assert row.ok is True
    detail = row.detail.lower()
    assert "stream_fallback_continue" in detail or "midstream" in detail
    assert "tool" in detail
    assert "fail" in detail or "incomplete" in detail or "closed" in detail


def test_tip_absent_when_stream_fallback_continue_disabled(settings):
    settings.routing.stream_fallback_continue = False
    assert _check_stream_fallback_continue(settings) is None
    rows = run_doctor(settings, httpx_client=None)
    assert not any(r.name == "stream_fallback_continue" for r in rows)
