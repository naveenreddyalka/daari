"""Invalid API-key throttle (#935)."""

from __future__ import annotations

from daari.auth.invalid_key_throttle import AuthThrottle
from daari.server.app import create_app
from daari.router.router import AppContext
from httpx import ASGITransport, AsyncClient
import pytest


def test_throttle_trips_after_max_failures():
    throttle = AuthThrottle(max_failures=3, window_seconds=60.0, exempt_loopback=False)
    ip = "203.0.113.9"
    assert throttle.check(ip).allowed is True
    for _ in range(3):
        throttle.record_failure(ip)
    denied = throttle.check(ip)
    assert denied.allowed is False
    assert denied.retry_after >= 1


def test_loopback_exempt_by_default():
    throttle = AuthThrottle(max_failures=1, window_seconds=60.0)
    assert throttle.record_failure("127.0.0.1") == 0
    assert throttle.check("127.0.0.1").allowed is True


def test_disabled_never_blocks():
    throttle = AuthThrottle(max_failures=1, enabled=False, exempt_loopback=False)
    throttle.record_failure("203.0.113.1")
    assert throttle.check("203.0.113.1").allowed is True


def test_redis_fail_open():
    class Boom:
        def get(self, key):
            raise RuntimeError("down")

        def incr(self, key):
            raise RuntimeError("down")

        def expire(self, key, seconds):
            raise RuntimeError("down")

    throttle = AuthThrottle(
        max_failures=1, window_seconds=60.0, exempt_loopback=False, redis=Boom()
    )
    # incr fails → local path still records
    assert throttle.record_failure("198.51.100.2") == 1
    # get fails → falls back to local count
    assert throttle.check("198.51.100.2").allowed is False


@pytest.mark.asyncio
async def test_gateway_returns_429_after_failures(settings, monkeypatch):
    settings.server.api_key = "master-secret"
    settings.auth.max_failures = 3
    settings.auth.window_seconds = 60.0
    settings.auth.exempt_loopback = False
    application = create_app(settings)
    application.state.ctx = AppContext.from_settings(settings)
    # Force a non-loopback peer for ASGITransport (defaults to 127.0.0.1).
    throttle = application.state.auth_throttle
    throttle.exempt_loopback = False

    transport = ASGITransport(app=application, client=("203.0.113.50", 50000))
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        for _ in range(3):
            bad = await client.get("/v1/models", headers={"Authorization": "Bearer wrong"})
            assert bad.status_code == 401
        throttled = await client.get("/v1/models", headers={"Authorization": "Bearer wrong"})
        assert throttled.status_code == 429
        assert throttled.headers.get("Retry-After")
        assert throttled.json()["error"]["code"] == "auth_throttled"
        ok = await client.get(
            "/v1/models", headers={"Authorization": "Bearer master-secret"}
        )
        assert ok.status_code == 200
    snap = application.state.ctx.metrics.snapshot(include_histograms=True)
    assert snap["rejects"].get("auth_throttled", 0) >= 1


@pytest.mark.asyncio
async def test_loopback_client_not_throttled(settings):
    settings.server.api_key = "master-secret"
    settings.auth.max_failures = 1
    settings.auth.exempt_loopback = True
    application = create_app(settings)
    application.state.ctx = AppContext.from_settings(settings)
    transport = ASGITransport(app=application)  # 127.0.0.1
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        for _ in range(3):
            bad = await client.get("/v1/models", headers={"Authorization": "Bearer wrong"})
            assert bad.status_code == 401
        still = await client.get("/v1/models", headers={"Authorization": "Bearer wrong"})
        assert still.status_code == 401
