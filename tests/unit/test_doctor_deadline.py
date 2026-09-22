"""Doctor warns when upstream.request_deadline_seconds is unset (#867)."""

from __future__ import annotations

import httpx

from daari.setup.doctor import _check_request_deadline, run_doctor


def _down_client() -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down", request=request)

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_warns_when_deadline_unset(settings):
    settings.upstream.request_deadline_seconds = None
    result = _check_request_deadline(settings)
    assert result.name == "request_deadline"
    assert result.ok is False
    assert result.optional is True
    assert "unset" in result.detail.lower() or "not set" in result.detail.lower()


def test_warns_when_deadline_zero(settings):
    settings.upstream.request_deadline_seconds = 0.0
    result = _check_request_deadline(settings)
    assert result.ok is False
    assert result.optional is True


def test_passes_when_deadline_positive(settings):
    settings.upstream.request_deadline_seconds = 30.0
    result = _check_request_deadline(settings)
    assert result.ok is True
    assert result.optional is True
    assert "30" in result.detail


def test_run_doctor_includes_check(settings):
    settings.upstream.request_deadline_seconds = None
    results = run_doctor(settings, httpx_client=_down_client())
    by_name = {r.name: r for r in results}
    assert "request_deadline" in by_name
    assert by_name["request_deadline"].ok is False
