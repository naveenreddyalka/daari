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


def test_unlock_clears_inprocess_and_redis():
    lock = KeyLockout(
        max_failures=1,
        window_seconds=60.0,
        lockout_seconds=30,
        exempt_loopback=False,
    )
    lock.record_failure("abcdefghijXXXX", client_ip="203.0.113.1")
    assert lock.check("abcdefghijYYYY", client_ip="203.0.113.2").allowed is False
    assert lock.unlock("abcdefghijZZZZ") is True
    assert lock.check("abcdefghijYYYY", client_ip="203.0.113.2").allowed is True

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

        def delete(self, *keys):
            removed = 0
            for key in keys:
                if key in self.data:
                    del self.data[key]
                    removed += 1
            return removed

        def keys(self, pattern):
            import fnmatch

            return [key for key in self.data if fnmatch.fnmatch(key, pattern)]

    redis = Store()
    remote = KeyLockout(
        max_failures=1,
        window_seconds=60.0,
        lockout_seconds=17,
        exempt_loopback=False,
        redis=redis,
    )
    remote.record_failure("abcdefghij0000", client_ip="203.0.113.4")
    assert remote.check("abcdefghij1111", client_ip="198.51.100.4").allowed is False
    assert remote.locked_prefixes() == ["abcdefghij"]
    assert remote.unlock("abcdefghij") is True
    assert remote.check("abcdefghij1111", client_ip="198.51.100.4").allowed is True
    assert remote.locked_prefixes() == []


@pytest.mark.asyncio
async def test_gateway_admin_unlock_then_request_succeeds(settings, tmp_path):
    settings.server.api_key = "master-secret"
    settings.auth.max_failures = 50
    settings.auth.exempt_loopback = False
    settings.auth.key_lockout.max_failures = 1
    settings.auth.key_lockout.lockout_seconds = 45
    settings.enterprise.audit_path = str(tmp_path / "audit.sqlite3")
    application = create_app(settings)
    application.state.ctx = AppContext.from_settings(settings)
    application.state.auth_throttle.exempt_loopback = False
    application.state.key_lockout.exempt_loopback = False

    transport = ASGITransport(app=application, client=("203.0.113.61", 50000))
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        bad = await client.get(
            "/v1/models", headers={"Authorization": "Bearer abcdefghijXXXX"}
        )
        assert bad.status_code == 401
        locked = await client.get(
            "/v1/models", headers={"Authorization": "Bearer abcdefghijYYYY"}
        )
        assert locked.status_code == 429
        unknown = await client.post(
            "/v1/daari/keys/unlock",
            json={"prefix": "abcdefghij"},
            headers={"Authorization": "Bearer not-admin"},
        )
        assert unknown.status_code == 401
        unlocked = await client.post(
            "/v1/daari/keys/unlock",
            json={"prefix": "abcdefghij"},
            headers={"Authorization": "Bearer master-secret"},
        )
        assert unlocked.status_code == 200
        assert unlocked.json()["prefix"] == "abcdefghij"
        again = await client.get(
            "/v1/models", headers={"Authorization": "Bearer abcdefghijYYYY"}
        )
        assert again.status_code == 401
    rows = audit_log_from_settings(settings).list(action="auth.key_unlocked")
    assert rows
    detail = rows[0].get("detail") or {}
    if isinstance(detail, str):
        import json

        detail = json.loads(detail)
    assert detail.get("prefix") == "abcdefghij"


def test_cli_unlock_prefix_clears_lock_and_audits(tmp_path, monkeypatch):
    from typer.testing import CliRunner

    from daari.cli.app import app as cli_app
    from daari.config.settings import Settings

    settings = Settings()
    settings.enterprise.audit_path = str(tmp_path / "audit.sqlite3")
    lock = KeyLockout(max_failures=1, window_seconds=60.0, exempt_loopback=False)
    lock.record_failure("abcdefghijXXXX", client_ip="203.0.113.9")
    monkeypatch.setattr("daari.cli.app.get_settings", lambda: settings)
    monkeypatch.setattr("daari.auth.key_lockout.build_key_lockout", lambda _settings: lock)
    monkeypatch.setattr(
        "daari.cli.app._daemon_unlock_prefix",
        lambda *_args, **_kwargs: (False, "daemon not running"),
    )
    result = CliRunner().invoke(cli_app, ["keys", "unlock-prefix", "abcdefghij"])
    assert result.exit_code == 0, result.output
    assert lock.check("abcdefghijYYYY", client_ip="203.0.113.9").allowed is True
    rows = audit_log_from_settings(settings).list(action="auth.key_unlocked")
    assert rows


def test_doctor_lockout_disabled_and_redis_prefixes(settings, monkeypatch):
    from daari.setup.doctor import _check_key_lockout

    settings.auth.key_lockout.enabled = False
    tip = _check_key_lockout(settings)
    assert tip.name == "key_lockout"
    assert tip.optional is True
    assert tip.ok is False
    assert "disabled" in tip.detail.lower()

    settings.auth.key_lockout.enabled = True
    settings.cache.backend = "redis"
    settings.cache.redis_url = "redis://127.0.0.1:6379/0"

    class Store:
        def ping(self):
            return True

        def keys(self, pattern):
            assert "lock:" in pattern
            return ["daari:auth_key_fail:lock:abcdefghij"]

    monkeypatch.setattr(
        "daari.cache.redis_client.connect_redis", lambda *_a, **_k: Store()
    )
    shown = _check_key_lockout(settings)
    assert shown.optional is True
    assert "abcdefghij" in shown.detail


def test_key_locked_webhook_signed_and_deduped(monkeypatch):
    import json

    import httpx

    from daari.config.settings import Settings
    from daari.observability.budget_alerts import sign_webhook
    from daari.auth.key_lockout_alerts import notify_key_locked, reset_key_locked_alerts

    reset_key_locked_alerts()
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(204)

    settings = Settings()
    settings.alerts.budget_webhook_url = "https://hooks.example/lock"
    settings.alerts.budget_webhook_secret = "whsec_test"
    transport = httpx.MockTransport(handler)
    assert notify_key_locked(
        settings,
        prefix="abcdefghij",
        failures=3,
        retry_after=45,
        transport=transport,
    )
    assert notify_key_locked(
        settings,
        prefix="abcdefghij",
        failures=3,
        retry_after=45,
        transport=transport,
    ) is False
    assert len(captured) == 1
    body = captured[0].content
    payload = json.loads(body)
    assert payload["event"] == "key_locked"
    assert payload["prefix"] == "abcdefghij"
    timestamp = captured[0].headers["X-Daari-Timestamp"]
    signature = captured[0].headers["X-Daari-Signature"]
    assert signature.split(",")[0] == sign_webhook(body, "whsec_test", timestamp)
