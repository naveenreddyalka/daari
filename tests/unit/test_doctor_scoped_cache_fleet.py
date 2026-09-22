"""Doctor warns scoped cache_scope on disk multi-replica fleets (#891)."""

from __future__ import annotations

import httpx

from daari.auth.virtual_keys import VirtualKeyStore
from daari.setup.doctor import _check_scoped_cache_fleet, run_doctor


def _down_client() -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down", request=request)

    return httpx.Client(transport=httpx.MockTransport(handler))


def _enable_vk(settings, tmp_path, *, cache_scope: str = "global"):
    settings.server.virtual_keys.enabled = True
    settings.server.virtual_keys.path = str(tmp_path / "vk.sqlite3")
    store = VirtualKeyStore(settings.virtual_keys_path)
    store.create("bot", client_id="bot", cache_scope=cache_scope)
    return store


def test_passes_single_replica_even_with_scoped_key(settings, tmp_path, monkeypatch):
    monkeypatch.setenv("DAARI_FLEET_REPLICAS", "1")
    settings.cache.backend = "disk"
    _enable_vk(settings, tmp_path, cache_scope="key")
    result = _check_scoped_cache_fleet(settings)
    assert result.name == "scoped_cache_fleet"
    assert result.ok is True
    assert result.optional is True


def test_passes_when_all_scopes_global(settings, tmp_path, monkeypatch):
    monkeypatch.setenv("DAARI_FLEET_REPLICAS", "3")
    settings.cache.backend = "disk"
    _enable_vk(settings, tmp_path, cache_scope="global")
    result = _check_scoped_cache_fleet(settings)
    assert result.ok is True


def test_passes_when_redis_backend(settings, tmp_path, monkeypatch):
    monkeypatch.setenv("DAARI_FLEET_REPLICAS", "3")
    settings.cache.backend = "redis"
    _enable_vk(settings, tmp_path, cache_scope="team")
    result = _check_scoped_cache_fleet(settings)
    assert result.ok is True


def test_fails_scoped_key_on_disk_multi_replica(settings, tmp_path, monkeypatch):
    monkeypatch.setenv("DAARI_FLEET_REPLICAS", "2")
    settings.cache.backend = "disk"
    _enable_vk(settings, tmp_path, cache_scope="key")
    result = _check_scoped_cache_fleet(settings)
    assert result.ok is False
    assert result.optional is True
    assert "cache_scope" in result.detail
    assert "redis" in result.detail.lower()


def test_fails_scoped_team_on_disk_multi_replica(settings, tmp_path, monkeypatch):
    monkeypatch.setenv("DAARI_FLEET_REPLICAS", "2")
    settings.cache.backend = "disk"
    settings.server.virtual_keys.enabled = True
    settings.server.virtual_keys.path = str(tmp_path / "vk.sqlite3")
    store = VirtualKeyStore(settings.virtual_keys_path)
    store.create_team("eng", cache_scope="team")
    store.create("bot", client_id="bot", team="eng")
    result = _check_scoped_cache_fleet(settings)
    assert result.ok is False
    assert "team" in result.detail.lower() or "cache_scope" in result.detail


def test_quiet_when_virtual_keys_disabled(settings, monkeypatch):
    monkeypatch.setenv("DAARI_FLEET_REPLICAS", "4")
    settings.cache.backend = "disk"
    settings.server.virtual_keys.enabled = False
    result = _check_scoped_cache_fleet(settings)
    assert result.ok is True


def test_run_doctor_includes_check(settings, tmp_path, monkeypatch):
    monkeypatch.setenv("DAARI_FLEET_REPLICAS", "2")
    settings.cache.backend = "disk"
    _enable_vk(settings, tmp_path, cache_scope="key")
    results = run_doctor(settings, httpx_client=_down_client())
    by_name = {r.name: r for r in results}
    assert "scoped_cache_fleet" in by_name
    assert by_name["scoped_cache_fleet"].ok is False
