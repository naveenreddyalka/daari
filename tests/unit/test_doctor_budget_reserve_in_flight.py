"""Doctor tip when budgets.reserve_in_flight is on without USD windows (#2290)."""

from __future__ import annotations

from daari.auth.virtual_keys import VirtualKeyStore
from daari.setup.doctor import _check_budget_reserve_in_flight, run_doctor


def _down_client():
    import httpx

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down", request=request)

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_tips_when_reserve_on_without_usd_windows(settings, tmp_path):
    settings.budgets.reserve_in_flight = True
    settings.server.virtual_keys.path = str(tmp_path / "vk.sqlite3")
    settings.server.virtual_keys.enabled = True
    VirtualKeyStore(settings.virtual_keys_path).create("bot", client_id="bot")
    result = _check_budget_reserve_in_flight(settings)
    assert result.ok is False
    assert result.optional is True
    assert "reserve_in_flight" in result.detail
    assert "USD" in result.detail or "budget" in result.detail.lower()


def test_quiet_when_reserve_off(settings, tmp_path):
    settings.budgets.reserve_in_flight = False
    settings.server.virtual_keys.path = str(tmp_path / "vk.sqlite3")
    settings.server.virtual_keys.enabled = True
    VirtualKeyStore(settings.virtual_keys_path).create("bot", client_id="bot")
    result = _check_budget_reserve_in_flight(settings)
    assert result.ok is True


def test_quiet_when_reserve_on_with_usd_window(settings, tmp_path):
    settings.budgets.reserve_in_flight = True
    settings.server.virtual_keys.path = str(tmp_path / "vk.sqlite3")
    settings.server.virtual_keys.enabled = True
    VirtualKeyStore(settings.virtual_keys_path).create(
        "bot", client_id="bot", daily_budget_usd=5.0
    )
    result = _check_budget_reserve_in_flight(settings)
    assert result.ok is True


def test_run_doctor_includes_check(settings, tmp_path):
    settings.budgets.reserve_in_flight = True
    settings.server.virtual_keys.path = str(tmp_path / "vk.sqlite3")
    settings.server.virtual_keys.enabled = True
    VirtualKeyStore(settings.virtual_keys_path).create("bot", client_id="bot")
    results = run_doctor(settings, httpx_client=_down_client())
    by_name = {r.name: r for r in results}
    assert "budget_reserve_in_flight" in by_name
    assert by_name["budget_reserve_in_flight"].ok is False
