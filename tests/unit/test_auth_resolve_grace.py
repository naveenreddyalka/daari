"""Opt-in last-known-good VK resolve grace across Postgres blips (#2163)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from daari.auth.postgres_virtual_keys import PostgresBackendUnavailable
from daari.auth.virtual_keys import VirtualKey
from daari.config.settings import AuthSettings
from daari.observability.metrics import Metrics
from daari.observability.prometheus import render_prometheus
from daari.server.auth import ResolveGraceCache, resolve_auth


class _RaisingStore:
    enabled = True
    unreachable = False

    def resolve(self, plaintext: str, *, now=None):
        raise PostgresBackendUnavailable("virtual_keys", "simulated")

    def list(self):
        raise PostgresBackendUnavailable("virtual_keys", "simulated")

    def get_team(self, team_id: str):
        raise PostgresBackendUnavailable("virtual_keys", "simulated")


class _OkStore:
    enabled = True
    unreachable = False

    def __init__(self, key: VirtualKey):
        self._key = key

    def resolve(self, plaintext: str, *, now=None):
        return self._key

    def list(self):
        return [self._key]

    def get_team(self, team_id: str):
        return None


def _vk(**kwargs) -> VirtualKey:
    defaults = dict(
        key_id="k1",
        name="test",
        prefix="sk-test",
        client_id="c1",
    )
    defaults.update(kwargs)
    return VirtualKey(**defaults)


def test_auth_settings_grace_ttl_default_zero():
    assert AuthSettings().resolve_grace_ttl_s == 0.0


def test_grace_serves_within_ttl():
    cache = ResolveGraceCache()
    key = _vk()
    ok = _OkStore(key)
    claims = resolve_auth(
        "sk-secret",
        master_key=None,
        store=ok,
        grace_cache=cache,
        grace_ttl_s=30.0,
    )
    assert claims is not None
    assert claims.kind == "virtual"
    assert claims.grace_served is False

    down = _RaisingStore()
    grace = resolve_auth(
        "sk-secret",
        master_key=None,
        store=down,
        grace_cache=cache,
        grace_ttl_s=30.0,
    )
    assert grace is not None
    assert grace.kind == "virtual"
    assert grace.key_id == "k1"
    assert grace.grace_served is True


def test_grace_fail_closed_past_ttl():
    cache = ResolveGraceCache()
    key = _vk()
    resolve_auth(
        "sk-secret",
        master_key=None,
        store=_OkStore(key),
        grace_cache=cache,
        grace_ttl_s=1.0,
    )
    entry = cache._entries[cache.hash_key("sk-secret")]
    entry.resolved_at -= 5.0
    with pytest.raises(PostgresBackendUnavailable):
        resolve_auth(
            "sk-secret",
            master_key=None,
            store=_RaisingStore(),
            grace_cache=cache,
            grace_ttl_s=1.0,
        )


def test_grace_disabled_fail_closed():
    cache = ResolveGraceCache()
    key = _vk()
    resolve_auth(
        "sk-secret",
        master_key=None,
        store=_OkStore(key),
        grace_cache=cache,
        grace_ttl_s=0.0,
    )
    with pytest.raises(PostgresBackendUnavailable):
        resolve_auth(
            "sk-secret",
            master_key=None,
            store=_RaisingStore(),
            grace_cache=cache,
            grace_ttl_s=0.0,
        )


def test_grace_never_serves_unknown_key():
    cache = ResolveGraceCache()
    with pytest.raises(PostgresBackendUnavailable):
        resolve_auth(
            "sk-never-seen",
            master_key=None,
            store=_RaisingStore(),
            grace_cache=cache,
            grace_ttl_s=60.0,
        )


def test_grace_skips_expired_cached_key():
    cache = ResolveGraceCache()
    expired = _vk(
        expires_at=(datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    )
    resolve_auth(
        "sk-expired",
        master_key=None,
        store=_OkStore(expired),
        grace_cache=cache,
        grace_ttl_s=60.0,
    )
    with pytest.raises(PostgresBackendUnavailable):
        resolve_auth(
            "sk-expired",
            master_key=None,
            store=_RaisingStore(),
            grace_cache=cache,
            grace_ttl_s=60.0,
        )


def test_grace_master_key_unchanged():
    claims = resolve_auth(
        "master-secret",
        master_key="master-secret",
        store=_RaisingStore(),
        grace_cache=ResolveGraceCache(),
        grace_ttl_s=60.0,
    )
    assert claims is not None
    assert claims.kind == "master"
    assert claims.grace_served is False


def test_auth_grace_prometheus_counter():
    metrics = Metrics()
    metrics.record_auth_grace_served()
    text = render_prometheus(metrics)
    assert "daari_auth_grace_served_total 1" in text
