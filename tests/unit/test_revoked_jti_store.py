"""Fleet-durable MCP OAuth revoked-jti denylist (#1498)."""

from __future__ import annotations

import time
import uuid


from daari.config.settings import Settings
from daari.gateway.mcp_oauth import (
    clear_revocation_denylist,
    configure_revocation_store,
    is_jti_revoked,
    revoke_jti,
)
from daari.gateway.revoked_jti_store import (
    InProcessRevokedJtiStore,
    PostgresRevokedJtiStore,
    RedisRevokedJtiStore,
    resolve_revocation_store,
)
from daari.setup.doctor import _check_mcp_oauth_revoke_fleet


def test_memory_postgres_store_shared_across_instances():
    dsn = f"memory:revoked-{uuid.uuid4().hex}"
    a = PostgresRevokedJtiStore(dsn)
    b = PostgresRevokedJtiStore(dsn)
    exp = int(time.time()) + 600
    a.revoke("jti-shared", exp)
    assert b.is_revoked("jti-shared") is True
    assert a.is_revoked("jti-shared") is True


def test_memory_postgres_store_prunes_expired():
    dsn = f"memory:revoked-prune-{uuid.uuid4().hex}"
    store = PostgresRevokedJtiStore(dsn)
    past = int(time.time()) - 10
    future = int(time.time()) + 600
    store.revoke("expired", past)  # exp in the past → no-op
    assert store.is_revoked("expired") is False
    store.revoke("keep", future)
    store.revoke("stale", future)
    from daari.gateway import revoked_jti_store as mod

    bucket, lock = mod._memory_bucket(dsn)
    with lock:
        bucket["stale"] = int(time.time()) - 1
    store.prune()
    assert store.is_revoked("stale") is False
    assert store.is_revoked("keep") is True


def test_redis_store_shared_via_injected_client():
    class FakeRedis:
        def __init__(self) -> None:
            self.data: dict[str, tuple[str, int | None]] = {}

        def set(self, key: str, value: str, exat: int | None = None, ex: int | None = None):
            self.data[key] = (value, exat if exat is not None else ex)

        def exists(self, key: str) -> int:
            return 1 if key in self.data else 0

        def scan_iter(self, match: str = "*"):
            prefix = match.rstrip("*")
            return [k for k in self.data if k.startswith(prefix)]

        def delete(self, *keys: str) -> int:
            n = 0
            for key in keys:
                if self.data.pop(key, None) is not None:
                    n += 1
            return n

    client = FakeRedis()
    a = RedisRevokedJtiStore("redis://fake", client=client)
    b = RedisRevokedJtiStore("redis://fake", client=client)
    exp = int(time.time()) + 120
    a.revoke("rjti", exp)
    assert b.is_revoked("rjti") is True
    assert client.data["daari:mcp:revoked:rjti"][1] == exp


def test_resolve_prefers_redis_then_postgres():
    settings = Settings()
    settings.cache.backend = "redis"
    settings.cache.redis_url = "redis://127.0.0.1:6379/0"
    store = resolve_revocation_store(settings)
    assert isinstance(store, RedisRevokedJtiStore)

    settings.cache.backend = "disk"
    settings.observability.postgres_url = "memory:resolve-pg"
    store = resolve_revocation_store(settings)
    assert isinstance(store, PostgresRevokedJtiStore)

    settings.observability.postgres_url = ""
    store = resolve_revocation_store(settings)
    assert isinstance(store, InProcessRevokedJtiStore)


def test_configure_revocation_store_wires_mcp_oauth_helpers():
    clear_revocation_denylist()
    settings = Settings()
    settings.observability.postgres_url = f"memory:wire-{uuid.uuid4().hex}"
    configure_revocation_store(settings)
    exp = int(time.time()) + 300
    revoke_jti("wired", exp)
    assert is_jti_revoked("wired") is True
    # Second configure with same DSN still sees the entry (shared bucket).
    other = Settings()
    other.observability.postgres_url = settings.observability.postgres_url
    configure_revocation_store(other)
    assert is_jti_revoked("wired") is True
    clear_revocation_denylist()
    assert is_jti_revoked("wired") is False


def test_doctor_warns_when_local_as_fleet_lacks_shared_store(monkeypatch):
    settings = Settings()
    settings.integrations.mcp_oauth.local_as = True
    settings.cache.backend = "disk"
    settings.observability.postgres_url = ""
    monkeypatch.setenv("DAARI_FLEET_REPLICAS", "2")
    result = _check_mcp_oauth_revoke_fleet(settings)
    assert result.ok is False
    assert "revoked jtis" in result.detail or "oauth/revoke" in result.detail


def test_doctor_ok_with_postgres_on_fleet(monkeypatch):
    settings = Settings()
    settings.integrations.mcp_oauth.local_as = True
    settings.observability.postgres_url = "postgresql://x/y"
    monkeypatch.setenv("DAARI_FLEET_REPLICAS", "3")
    result = _check_mcp_oauth_revoke_fleet(settings)
    assert result.ok is True
    assert "postgres" in result.detail


def test_doctor_ok_single_replica_documents_ephemeral(monkeypatch):
    settings = Settings()
    settings.integrations.mcp_oauth.local_as = True
    monkeypatch.setenv("DAARI_FLEET_REPLICAS", "1")
    result = _check_mcp_oauth_revoke_fleet(settings)
    assert result.ok is True
    assert "not backup-critical" in result.detail or "single replica" in result.detail
