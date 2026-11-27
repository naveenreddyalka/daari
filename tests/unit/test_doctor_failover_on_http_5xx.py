"""Doctor tip when upstream.retry.failover_on_http_5xx is enabled (#2336)."""

from __future__ import annotations

from pathlib import Path

from daari.setup.doctor import _check_failover_on_http_5xx, run_doctor

DOCTOR_HEALTH = Path("docs/developer/guides/operations/doctor-health.md")


def _down_client():
    import httpx

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down", request=request)

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_tips_when_failover_on_http_5xx_enabled(settings):
    settings.upstream.retry.failover_on_http_5xx = True
    row = _check_failover_on_http_5xx(settings)
    assert row is not None
    assert row.name == "failover_on_http_5xx"
    assert row.ok is True
    assert row.optional is True
    detail = row.detail
    assert "upstream.retry.failover_on_http_5xx" in detail
    assert "501" in detail
    assert "522" in detail
    assert "500" in detail or "5xx" in detail.lower()


def test_quiet_when_failover_on_http_5xx_disabled(settings):
    settings.upstream.retry.failover_on_http_5xx = False
    assert _check_failover_on_http_5xx(settings) is None


def test_run_doctor_includes_tip_when_enabled(settings):
    settings.upstream.retry.failover_on_http_5xx = True
    rows = run_doctor(settings, httpx_client=_down_client())
    tip = next(r for r in rows if r.name == "failover_on_http_5xx")
    assert tip.ok is True
    assert tip.optional is True
    assert "failover_on_http_5xx" in tip.detail


def test_run_doctor_omits_tip_when_disabled(settings):
    settings.upstream.retry.failover_on_http_5xx = False
    rows = run_doctor(settings, httpx_client=_down_client())
    assert all(r.name != "failover_on_http_5xx" for r in rows)


def test_doctor_health_docs_pin_failover_on_http_5xx_row():
    text = DOCTOR_HEALTH.read_text(encoding="utf-8")
    assert "doctor `failover_on_http_5xx`" in text
    assert "upstream.retry.failover_on_http_5xx" in text
