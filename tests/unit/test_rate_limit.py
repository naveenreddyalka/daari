"""Distributed rate limiting: RPM/TPM, concurrency, Redis vs SQLite (issue #169)."""

from __future__ import annotations

import asyncio
import time

import pytest
from httpx import ASGITransport, AsyncClient

from daari.auth.rate_limit import (
    MemoryCounterBackend,
    RateLimiter,
    RedisCounterBackend,
    SqliteCounterBackend,
    build_rate_limiter,
)
from daari.gateway.internal import DaariMeta, InternalRequest, InternalResponse
from daari.router.router import AppContext
from daari.server.app import create_app


CHAT = {"model": "daari", "messages": [{"role": "user", "content": "hi"}]}


class FakeRedis:
    """Minimal INCR/EXPIRE/GET/TTL stand-in — no real Redis process."""

    def __init__(self) -> None:
        self.store: dict[str, int] = {}
        self.ttls: dict[str, int] = {}
        self.incr_calls = 0

    def incrby(self, key: str, amount: int = 1) -> int:
        self.incr_calls += 1
        self.store[key] = self.store.get(key, 0) + amount
        return self.store[key]

    def incr(self, key: str) -> int:
        return self.incrby(key, 1)

    def expire(self, key: str, seconds: int) -> bool:
        self.ttls[key] = seconds
        return True

    def get(self, key: str) -> str | None:
        value = self.store.get(key)
        return None if value is None else str(value)

    def ttl(self, key: str) -> int:
        return self.ttls.get(key, -1)

    def pipeline(self):
        return _FakePipeline(self)


class _FakePipeline:
    def __init__(self, redis: FakeRedis) -> None:
        self.redis = redis
        self._ops: list = []

    def incrby(self, key: str, amount: int = 1):
        self._ops.append(("incrby", key, amount))
        return self

    def expire(self, key: str, seconds: int):
        self._ops.append(("expire", key, seconds))
        return self

    def execute(self) -> list:
        results = []
        for op in self._ops:
            if op[0] == "incrby":
                results.append(self.redis.incrby(op[1], op[2]))
            elif op[0] == "expire":
                results.append(self.redis.expire(op[1], op[2]))
        self._ops.clear()
        return results


def _app(settings, *, limiter: RateLimiter | None = None):
    application = create_app(settings)
    application.state.ctx = AppContext.from_settings(settings)
    if limiter is not None:
        application.state.rate_limiter = limiter

    async def fake(request: InternalRequest) -> InternalResponse:
        return InternalResponse(
            content="ok",
            model="llama3.2:3b",
            daari_meta=DaariMeta(tier="L3", executor="ollama", latency_ms=1),
        )

    application.state.ctx.router.ollama.execute = fake
    return application


class TestCounterBackends:
    def test_memory_increments_in_window(self):
        backend = MemoryCounterBackend()
        assert backend.increment("k", 1) == 1
        assert backend.increment("k", 1) == 2
        assert backend.name == "memory"

    def test_sqlite_increments(self, tmp_path):
        backend = SqliteCounterBackend(tmp_path / "rl.sqlite3")
        assert backend.increment("k", 1) == 1
        assert backend.increment("k", 2) == 3
        assert backend.name == "sqlite"

    def test_redis_increments_without_sqlite(self, tmp_path, monkeypatch):
        fake = FakeRedis()
        backend = RedisCounterBackend(client=fake, prefix="daari:rl:")
        connects: list = []
        monkeypatch.setattr(
            "sqlite3.connect",
            lambda *args, **kwargs: connects.append(args) or (_ for _ in ()).throw(AssertionError("sqlite")),
        )
        assert backend.increment("k", 1) == 1
        assert backend.increment("k", 1) == 2
        assert backend.name == "redis"
        assert fake.incr_calls == 2
        assert connects == []


class TestRateLimiter:
    def test_rpm_per_key(self):
        limiter = RateLimiter(MemoryCounterBackend(), default_rpm=2)
        first = limiter.check(key_id="alice", model="daari", tokens=1)
        second = limiter.check(key_id="alice", model="daari", tokens=1)
        third = limiter.check(key_id="alice", model="daari", tokens=1)
        assert first.allowed and second.allowed
        assert not third.allowed
        assert third.scope == "rpm"
        assert third.remaining == 0

    def test_rpm_per_model_is_independent(self):
        limiter = RateLimiter(MemoryCounterBackend(), default_rpm=10, model_rpm=1)
        a1 = limiter.check(key_id="alice", model="m1", tokens=1)
        a2 = limiter.check(key_id="alice", model="m1", tokens=1)
        b1 = limiter.check(key_id="alice", model="m2", tokens=1)
        assert a1.allowed
        assert not a2.allowed
        assert a2.scope == "rpm"
        assert b1.allowed

    def test_tpm_per_key(self):
        limiter = RateLimiter(MemoryCounterBackend(), default_tpm=10)
        first = limiter.check(key_id="alice", model="daari", tokens=8)
        second = limiter.check(key_id="alice", model="daari", tokens=8)
        assert first.allowed
        assert not second.allowed
        assert second.scope == "tpm"

    def test_unlimited_when_limits_are_zero(self):
        limiter = RateLimiter(MemoryCounterBackend())
        for _ in range(5):
            assert limiter.check(key_id="anon", model="daari", tokens=100).allowed

    def test_headers_fields_are_populated(self):
        limiter = RateLimiter(MemoryCounterBackend(), default_rpm=5)
        decision = limiter.check(key_id="alice", model="daari", tokens=1)
        assert decision.limit == 5
        assert decision.remaining == 4
        assert decision.reset_epoch >= int(time.time())


class TestBuildRateLimiter:
    def test_sqlite_when_cache_is_disk(self, settings, tmp_path):
        settings.cache.backend = "disk"
        limiter = build_rate_limiter(settings)
        assert limiter.backend.name == "sqlite"

    def test_redis_when_cache_backend_is_redis(self, settings):
        settings.cache.backend = "redis"
        fake = FakeRedis()
        limiter = build_rate_limiter(settings, redis_client=fake)
        assert limiter.backend.name == "redis"
        limiter.check(key_id="k", model="m", tokens=1, rpm=3)
        assert fake.incr_calls >= 1


@pytest.mark.asyncio
async def test_response_carries_ratelimit_headers(settings):
    settings.rate_limit.rpm = 10
    app = _app(settings)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/v1/chat/completions", json=CHAT)
    assert response.status_code == 200
    assert response.headers["x-ratelimit-limit"] == "10"
    assert int(response.headers["x-ratelimit-remaining"]) >= 0
    assert int(response.headers["x-ratelimit-reset"]) >= int(time.time())


@pytest.mark.asyncio
async def test_tpm_over_limit_is_429(settings):
    settings.rate_limit.tpm = 2
    app = _app(settings)
    fat = {
        "model": "daari",
        "messages": [{"role": "user", "content": "x" * 80}],
    }
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/v1/chat/completions", json=fat)
    assert response.status_code == 429
    assert response.json()["error"]["type"] == "rate_limit_error"
    assert "x-ratelimit-limit" in response.headers


@pytest.mark.asyncio
async def test_concurrency_overflow_is_503_with_retry_after(settings):
    settings.rate_limit.max_in_flight = 1
    settings.rate_limit.queue_size = 0
    app = _app(settings)
    await app.state.rate_limiter.acquire()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        overflow = await client.post("/v1/chat/completions", json=CHAT)
    await app.state.rate_limiter.release()
    assert overflow.status_code == 503
    assert overflow.headers.get("retry-after")
    assert overflow.json()["error"]["type"] == "rate_limit_error"


@pytest.mark.asyncio
async def test_concurrency_cap_holds_under_burst():
    limiter = RateLimiter(
        MemoryCounterBackend(), max_in_flight=2, queue_size=1, retry_after_seconds=1
    )
    current = 0
    peak = 0
    rejected = 0
    lock = asyncio.Lock()

    async def worker() -> None:
        nonlocal current, peak, rejected
        slot = await limiter.acquire()
        if not slot.allowed:
            rejected += 1
            return
        async with lock:
            current += 1
            peak = max(peak, current)
        await asyncio.sleep(0.02)
        async with lock:
            current -= 1
        await limiter.release()

    await asyncio.gather(*[worker() for _ in range(20)])
    assert peak <= 2
    assert rejected >= 1


@pytest.mark.asyncio
async def test_metrics_exposes_limits_and_utilization(settings):
    settings.rate_limit.rpm = 20
    settings.rate_limit.max_in_flight = 4
    settings.observability.prometheus = True
    app = _app(settings)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.post("/v1/chat/completions", json=CHAT)
        metrics = await client.get("/metrics")
    assert metrics.status_code == 200
    text = metrics.text
    assert "daari_rate_limit_limit" in text
    assert "daari_rate_limit_in_flight" in text
    assert "daari_rate_limit_in_flight_max" in text
