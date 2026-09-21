"""Doctor surfaces local_pool.frontier_fallback findings (#879)."""

from __future__ import annotations

import httpx

from daari.setup.doctor import _check_local_pool_frontier_fallback, run_doctor


def _down_client() -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down", request=request)

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_quiet_when_failover_off(settings):
    settings.routing.local_pool.frontier_fallback = False
    result = _check_local_pool_frontier_fallback(settings)
    assert result.name == "local_pool_frontier_fallback"
    assert result.ok is True
    assert result.optional is True


def test_warns_when_failover_on_frontier_disabled(settings):
    settings.routing.local_pool.frontier_fallback = True
    settings.frontier.enabled = False
    result = _check_local_pool_frontier_fallback(settings)
    assert result.ok is False
    assert result.optional is True
    assert "frontier.enabled" in result.detail


def test_passes_when_failover_on_frontier_enabled(settings):
    settings.routing.local_pool.frontier_fallback = True
    settings.frontier.enabled = True
    result = _check_local_pool_frontier_fallback(settings)
    assert result.ok is True


def test_run_doctor_includes_check(settings):
    settings.routing.local_pool.frontier_fallback = True
    settings.frontier.enabled = False
    results = run_doctor(settings, httpx_client=_down_client())
    by_name = {r.name: r for r in results}
    assert "local_pool_frontier_fallback" in by_name
    assert by_name["local_pool_frontier_fallback"].ok is False
