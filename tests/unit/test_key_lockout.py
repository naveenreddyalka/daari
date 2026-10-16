"""Per-key soft lockout on invalid-auth storms (#1684)."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from daari.auth.key_lockout import KeyLockout
from daari.enterprise.postgres_audit import audit_log_from_settings
from daari.router.router import AppContext
from daari.server.app import create_app


def test_lockout_trips_for_same_prefix_across_ips():
    lock = KeyLockout(
        max_failures=2,
        window_seconds=60.0,
        lockout_seconds=30,
        exempt_loopback=False,
    )
    assert lock.check("abcdefghijXXXX", client_ip="203.0.113.1").allowed is True
    lock.record_failure("abcdefghijXXXX", client_ip="203.0.113.1")
    lock.record_failure("abcdefghijYYYY", client_ip="203.0.113.2")
    denied = lock.check("abcdefghijZZZZ", client_ip="198.51.100.8")
    assert denied.allowed is False
    assert denied.retry_after >= 1
    assert denied.prefix == "abcdefghij"
    other = lock.check("zzzzzzzzzzAAAA", client_ip="203.0.113.1")
    assert other.allowed is True


def test_loopback_exempt_by_default():
    lock = KeyLockout(max_failures=1, window_seconds=60.0)
    assert lock.record_failure("stolen-key", client_ip="127.0.0.1") == 0
    assert lock.check("stolen-key", client_ip="127.0.0.1").allowed is True


def test_disabled_never_blocks():
    lock = KeyLockout(max_failures=1, enabled=False, exempt_loopback=False)
    lock.record_failure("stolen-key", client_ip="203.0.113.9")
    assert lock.check("stolen-key", client_ip="203.0.113.9").allowed is True


def test_redis_lock_and_fail_open():
    class Store:
        def __init__(self) -> None:
            self.data: dict[str, object] = {}

        def get(self, key):
            return self.data.get(key)

        def incr(self, key):
            self.data[key] = int(self.data.get(key) or 0) + 1
            return self.data[key]

        def expire(self, key, seconds):
            return True

        def set(self, key, value, ex=None):
            self.data[key] = value
            return True

        def ttl(self, key):
            return 17

    redis = Store()
    lock = KeyLockout(
        max_failures=1,
        window_seconds=60.0,
        lockout_seconds=17,
        exempt_loopback=False,
        redis=redis,
    )
    assert lock.record_failure("abcdefghij0000", client_ip="203.0.113.4") == 1
    denied = lock.check("abcdefghij1111", client_ip="198.51.100.4")
    assert denied.allowed is False
    assert denied.retry_after == 17

    class Boom:
        def get(self, key):
            raise RuntimeError("down")

        def incr(self, key):
            raise RuntimeError("down")

        def expire(self, key, seconds):
            raise RuntimeError("down")

        def set(self, key, value, ex=None):
            raise RuntimeError("down")

    broken = KeyLockout(
        max_failures=1, window_seconds=60.0, exempt_loopback=False, redis=Boom()
    )
    assert broken.record_failure("abcdefghij0000", client_ip="203.0.113.5") == 1
    assert broken.check("abcdefghij0000", client_ip="203.0.113.5").allowed is False


@pytest.mark.asyncio
async def test_gateway_key_lockout_independent_of_ip(settings, tmp_path):
    settings.server.api_key = "master-secret"
    settings.auth.max_failures = 50
    settings.auth.exempt_loopback = False
    settings.auth.key_lockout.max_failures = 2
    settings.auth.key_lockout.lockout_seconds = 45
    settings.enterprise.audit_path = str(tmp_path / "audit.sqlite3")
    application = create_app(settings)
    application.state.ctx = AppContext.from_settings(settings)
    application.state.auth_throttle.exempt_loopback = False
    application.state.key_lockout.exempt_loopback = False

    transport = ASGITransport(app=application, client=("203.0.113.60", 50000))
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        for _ in range(2):
            bad = await client.get(
                "/v1/models", headers={"Authorization": "Bearer abcdefghijXXXX"}
            )
            assert bad.status_code == 401
        locked = await client.get(
            "/v1/models", headers={"Authorization": "Bearer abcdefghijYYYY"}
        )
        assert locked.status_code == 429
        assert locked.headers.get("Retry-After")
        assert locked.json()["error"]["code"] == "auth_key_locked"
        other = await client.get(
            "/v1/models", headers={"Authorization": "Bearer zzzzzzzzzzYYYY"}
        )
        assert other.status_code == 401
        ok = await client.get(
            "/v1/models", headers={"Authorization": "Bearer master-secret"}
        )
        assert ok.status_code == 200
    snap = application.state.ctx.metrics.snapshot(include_histograms=True)
    assert snap["rejects"].get("auth_key_locked", 0) >= 1
    rows = audit_log_from_settings(settings).list(action="auth.key_locked")
    assert rows
    detail = rows[0].get("detail") or {}
    if isinstance(detail, str):
        import json

        detail = json.loads(detail)
    assert detail.get("scope") == "key"
    assert detail.get("prefix") == "abcdefghij"
    assert "abcdefghijXXXX" not in str(detail)
