"""Distributed rate limiting: RPM/TPM, concurrency, Redis vs SQLite (issue #169)."""

from __future__ import annotations

import asyncio
import time

import httpx
import pytest
from httpx import ASGITransport, AsyncClient

from daari.auth.rate_limit import (
    MemoryCounterBackend,
    RATELIMIT_WARNING_HEADER,
    RateLimiter,
    RedisCounterBackend,
    SqliteCounterBackend,
    build_rate_limiter,
    estimate_audio_upload_tokens,
    estimate_request_tokens,
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

    def ping(self) -> bool:
        return True


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
            lambda *args, **kwargs: (
                connects.append(args) or (_ for _ in ()).throw(AssertionError("sqlite"))
            ),
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

    def test_rpm_soft_band_before_hard_deny(self):
        limiter = RateLimiter(MemoryCounterBackend(), default_rpm=5)
        soft_ratio = 0.8
        decisions = [limiter.check(key_id="alice", model="daari", tokens=1) for _ in range(5)]
        # used 1..5 against limit 5; soft at >=4 (0.8).
        assert all(d.allowed for d in decisions)
        assert [d.in_soft_band(soft_ratio) for d in decisions] == [
            False,
            False,
            False,
            True,
            True,
        ]
        hard = limiter.check(key_id="alice", model="daari", tokens=1)
        assert not hard.allowed
        assert hard.scope == "rpm"
        assert not hard.in_soft_band(soft_ratio)
        assert RATELIMIT_WARNING_HEADER not in hard.headers()
        soft_headers = decisions[3].headers(soft=True)
        assert soft_headers[RATELIMIT_WARNING_HEADER] == "soft"


@pytest.mark.asyncio
async def test_rpm_soft_warn_header_then_hard_429(settings, monkeypatch):
    """Crossing soft_budget_ratio warns; exceeding RPM still 429s (#518).

    Freeze wall clock mid-window so a 60s counter rollover mid-loop cannot
    reset RPM counts and drop the soft header (CI flake).
    """
    monkeypatch.setattr(time, "time", lambda: 1_700_000_030.0)
    settings.frontier.soft_budget_ratio = 0.8
    app = _app(settings, limiter=RateLimiter(MemoryCounterBackend(), default_rpm=5))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        bodies = []
        for i in range(5):
            response = await client.post(
                "/v1/chat/completions",
                json=CHAT,
                headers={"X-Daari-Meta": "true", "X-Daari-No-Cache": "true"},
            )
            bodies.append(response)
            assert response.status_code == 200, response.text
            if i < 3:
                assert RATELIMIT_WARNING_HEADER not in response.headers
            else:
                assert response.headers[RATELIMIT_WARNING_HEADER] == "soft"
                assert response.json()["daari_meta"]["warning"] == "rate_limit_warning"
        hard = await client.post("/v1/chat/completions", json=CHAT)
    assert hard.status_code == 429
    assert hard.json()["error"]["type"] == "rate_limit_error"
    assert "x-ratelimit-limit" in hard.headers
    assert RATELIMIT_WARNING_HEADER not in hard.headers


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
async def test_high_priority_waiter_admitted_before_earlier_normal():
    """#848: priority class beats FIFO order at the in-flight gate."""
    limiter = RateLimiter(
        MemoryCounterBackend(), max_in_flight=1, queue_size=8, retry_after_seconds=1
    )
    order: list[str] = []
    started = asyncio.Event()

    async def hold() -> None:
        slot = await limiter.acquire(priority="normal")
        assert slot.allowed
        started.set()
        await asyncio.sleep(0.05)
        await limiter.release()

    async def wait(label: str, priority: str, delay: float) -> None:
        await started.wait()
        await asyncio.sleep(delay)
        slot = await limiter.acquire(priority=priority)
        assert slot.allowed
        order.append(label)
        await limiter.release()

    await asyncio.gather(
        hold(),
        wait("normal", "normal", 0.0),
        wait("high", "high", 0.01),
    )
    assert order == ["high", "normal"]


@pytest.mark.asyncio
async def test_batch_low_priority_yields_to_interactive():
    """#848: batch acquire(low) loses to interactive normal when contended."""
    limiter = RateLimiter(
        MemoryCounterBackend(), max_in_flight=1, queue_size=8, retry_after_seconds=1
    )
    order: list[str] = []

    # Hold the sole slot as batch would, then admit interactive before batch waiters.
    hold = await limiter.acquire(priority="low")
    assert hold.allowed

    async def interactive() -> None:
        await asyncio.sleep(0.01)
        slot = await limiter.acquire(priority="normal")
        assert slot.allowed
        order.append("interactive")
        await limiter.release()

    async def batch_waiter() -> None:
        await asyncio.sleep(0.0)
        slot = await limiter.acquire(priority="low")
        assert slot.allowed
        order.append("batch")
        await limiter.release()

    waiter_i = asyncio.create_task(interactive())
    waiter_b = asyncio.create_task(batch_waiter())
    await asyncio.sleep(0.02)
    await limiter.release()
    await asyncio.gather(waiter_i, waiter_b)
    assert order == ["interactive", "batch"]


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


class BoomRedis(FakeRedis):
    """Raises ConnectionError on every counter mutation (issue #463)."""

    def incrby(self, key: str, amount: int = 1) -> int:
        raise ConnectionError("redis down")

    def ping(self) -> bool:
        raise ConnectionError("redis down")


class BlockingRedis(FakeRedis):
    """Blocks then raises TimeoutError — simulates hung Redis past socket_timeout."""

    def __init__(self, block_seconds: float = 0.05) -> None:
        super().__init__()
        self.block_seconds = block_seconds

    def incrby(self, key: str, amount: int = 1) -> int:
        time.sleep(self.block_seconds)
        raise TimeoutError("socket timeout")

    def ping(self) -> bool:
        time.sleep(self.block_seconds)
        raise TimeoutError("socket timeout")


class RecoveringRedis(FakeRedis):
    """Fails until `heal()` is called — recovery without restart (#463)."""

    def __init__(self) -> None:
        super().__init__()
        self.down = True

    def incrby(self, key: str, amount: int = 1) -> int:
        if self.down:
            raise ConnectionError("redis down")
        return super().incrby(key, amount)

    def ping(self) -> bool:
        if self.down:
            raise ConnectionError("redis down")
        return True

    def heal(self) -> None:
        self.down = False


def test_redis_counter_passes_socket_timeouts(monkeypatch):
    captured: dict = {}

    class _FakeMod:
        class Redis:
            @staticmethod
            def from_url(url, **kwargs):
                captured.update(kwargs)
                captured["url"] = url
                return FakeRedis()

    monkeypatch.setitem(__import__("sys").modules, "redis", _FakeMod())
    backend = RedisCounterBackend(redis_url="redis://example:6379/0", timeout_seconds=2.5)
    backend.increment("k", 1)
    assert captured["url"] == "redis://example:6379/0"
    assert captured["decode_responses"] is True
    assert captured["socket_connect_timeout"] == 2.5
    assert captured["socket_timeout"] == 2.5


def test_rate_limiter_degrades_to_sqlite_on_redis_error(tmp_path, monkeypatch):
    events: list[tuple[str, dict]] = []

    def capture(event: str, detail=None, **kwargs):
        events.append((event, detail or {}))

    monkeypatch.setattr("daari.gateway.request_log.log_gateway_event", capture)
    redis = BoomRedis()
    fallback = SqliteCounterBackend(tmp_path / "rl.sqlite3")
    limiter = RateLimiter(
        RedisCounterBackend(client=redis),
        default_rpm=10,
        fallback_backend=fallback,
        probe_interval_seconds=0.0,
    )
    first = limiter.check(key_id="alice", model="daari", tokens=1)
    second = limiter.check(key_id="alice", model="daari", tokens=1)
    assert first.allowed and second.allowed
    assert first.backend == "sqlite"
    assert second.backend == "sqlite"
    assert limiter.backend.name == "sqlite"
    assert limiter.degraded is True
    assert sum(1 for e, _ in events if e == "rate_limit.degraded") == 1


def test_rate_limiter_fail_open_allows_without_sqlite(tmp_path, monkeypatch):
    events: list = []
    monkeypatch.setattr(
        "daari.gateway.request_log.log_gateway_event",
        lambda event, detail=None, **kw: events.append(event),
    )
    connects: list = []
    monkeypatch.setattr(
        "sqlite3.connect",
        lambda *args, **kwargs: (
            connects.append(args) or (_ for _ in ()).throw(AssertionError("sqlite should not open"))
        ),
    )
    limiter = RateLimiter(
        RedisCounterBackend(client=BoomRedis()),
        default_rpm=1,
        fail_open=True,
        fallback_backend=SqliteCounterBackend(tmp_path / "unused.sqlite3"),
    )
    # Many requests past the rpm=1 cap — fail-open must allow, not count in sqlite.
    for _ in range(5):
        decision = limiter.check(key_id="alice", model="daari", tokens=1)
        assert decision.allowed
    assert "rate_limit.degraded" in events
    assert connects == []


def test_rate_limiter_recovers_when_redis_returns(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "daari.gateway.request_log.log_gateway_event",
        lambda *args, **kwargs: None,
    )
    redis = RecoveringRedis()
    fallback = SqliteCounterBackend(tmp_path / "rl.sqlite3")
    limiter = RateLimiter(
        RedisCounterBackend(client=redis),
        default_rpm=100,
        fallback_backend=fallback,
        probe_interval_seconds=0.0,
    )
    assert limiter.check(key_id="a", model="m", tokens=1).backend == "sqlite"
    assert limiter.degraded is True
    redis.heal()
    recovered = limiter.check(key_id="a", model="m", tokens=1)
    assert recovered.backend == "redis"
    assert limiter.degraded is False
    assert redis.incr_calls >= 1


def test_rate_limit_degraded_prometheus_gauge(tmp_path, monkeypatch):
    from daari.observability.metrics import Metrics
    from daari.observability.prometheus import render_prometheus

    events: list = []
    monkeypatch.setattr(
        "daari.gateway.request_log.log_gateway_event",
        lambda event, detail=None, **kw: events.append(event),
    )
    redis = RecoveringRedis()
    fallback = SqliteCounterBackend(tmp_path / "rl.sqlite3")
    limiter = RateLimiter(
        RedisCounterBackend(client=redis),
        default_rpm=100,
        fallback_backend=fallback,
        probe_interval_seconds=0.0,
    )
    assert limiter.check(key_id="a", model="m", tokens=1).backend == "sqlite"
    assert limiter.degraded is True
    assert sum(1 for e in events if e == "rate_limit.degraded") == 1
    snap = limiter.snapshot()
    assert snap["degraded"] is True
    assert snap["degrade_mode"] == "sqlite_fallback"
    text = render_prometheus(Metrics(), rate_limit=snap)
    assert 'daari_rate_limit_degraded{mode="sqlite_fallback"} 1' in text
    assert 'daari_rate_limit_degraded{mode="fail_open"} 0' in text

    redis.heal()
    assert limiter.check(key_id="a", model="m", tokens=1).backend == "redis"
    assert limiter.degraded is False
    recovered = render_prometheus(Metrics(), rate_limit=limiter.snapshot())
    assert 'daari_rate_limit_degraded{mode="sqlite_fallback"} 0' in recovered
    assert 'daari_rate_limit_degraded{mode="fail_open"} 0' in recovered
    assert sum(1 for e in events if e == "rate_limit.degraded") == 1


def test_rate_limit_fail_open_prometheus_gauge(tmp_path, monkeypatch):
    from daari.observability.metrics import Metrics
    from daari.observability.prometheus import render_prometheus

    monkeypatch.setattr(
        "daari.gateway.request_log.log_gateway_event",
        lambda *args, **kwargs: None,
    )
    limiter = RateLimiter(
        RedisCounterBackend(client=BoomRedis()),
        default_rpm=10,
        fail_open=True,
        fallback_backend=SqliteCounterBackend(tmp_path / "unused.sqlite3"),
    )
    assert limiter.check(key_id="a", model="m", tokens=1).allowed
    text = render_prometheus(Metrics(), rate_limit=limiter.snapshot())
    assert 'daari_rate_limit_degraded{mode="fail_open"} 1' in text
    assert 'daari_rate_limit_degraded{mode="sqlite_fallback"} 0' in text


@pytest.mark.asyncio
async def test_gateway_survives_redis_connection_error(settings, tmp_path, monkeypatch):
    settings.cache.backend = "redis"
    settings.rate_limit.rpm = 10
    settings.server.virtual_keys.path = str(tmp_path / "vk.sqlite3")
    events: list[str] = []
    monkeypatch.setattr(
        "daari.gateway.request_log.log_gateway_event",
        lambda event, detail=None, **kw: events.append(event),
    )
    limiter = build_rate_limiter(settings, redis_client=BoomRedis())
    app = _app(settings, limiter=limiter)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/v1/chat/completions", json=CHAT)
    assert response.status_code == 200
    assert response.headers["x-ratelimit-limit"] == "10"
    assert response.headers.get("x-ratelimit-backend") == "sqlite"
    assert limiter.backend.name == "sqlite"
    assert "rate_limit.degraded" in events


@pytest.mark.asyncio
async def test_gateway_survives_redis_timeout(settings, tmp_path, monkeypatch):
    settings.cache.backend = "redis"
    settings.cache.redis_timeout_seconds = 2.0
    settings.rate_limit.rpm = 5
    settings.server.virtual_keys.path = str(tmp_path / "vk.sqlite3")
    monkeypatch.setattr(
        "daari.gateway.request_log.log_gateway_event",
        lambda *args, **kwargs: None,
    )
    limiter = build_rate_limiter(settings, redis_client=BlockingRedis(block_seconds=0.01))
    app = _app(settings, limiter=limiter)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/v1/chat/completions", json=CHAT)
    assert response.status_code == 200
    assert response.headers.get("x-ratelimit-backend") == "sqlite"


class _TokenSpy(RateLimiter):
    def __init__(self, **kwargs):
        super().__init__(MemoryCounterBackend(), **kwargs)
        self.tokens: list[int] = []

    def check(self, **kwargs):
        self.tokens.append(int(kwargs["tokens"]))
        return super().check(**kwargs)


def test_audio_upload_tokens_use_file_bytes_not_one():
    audio = b"x" * 4000
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["ct"] = request.headers["content-type"]
        captured["body"] = request.content
        return httpx.Response(200)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        client.post(
            "http://test/v1/audio/transcriptions",
            files={"file": ("note.wav", audio, "audio/wav")},
            data={"model": "whisper-1"},
        )
    tokens = estimate_audio_upload_tokens(captured["body"], captured["ct"])
    assert tokens == len(audio) // 4
    assert tokens >= 1000
    chat = {"model": "daari", "messages": [{"role": "user", "content": "a" * 16}]}
    assert estimate_request_tokens(chat) == 16 // 4
    embed = {"model": "daari", "input": "b" * 20}
    assert estimate_request_tokens(embed) == 20 // 4


@pytest.mark.asyncio
async def test_transcription_tpm_counts_file_bytes_chat_stays_chars(settings):
    """Multipart ASR charges len(file)//4; JSON chat and embeddings stay chars//4 (#765)."""
    spy = _TokenSpy(default_tpm=1_000_000)
    app = _app(settings, limiter=spy)
    audio = b"y" * 4000
    chat = {"model": "daari", "messages": [{"role": "user", "content": "a" * 16}]}
    embed = {"model": "daari", "input": "b" * 20}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        chat_response = await client.post("/v1/chat/completions", json=chat)
        embed_response = await client.post("/v1/embeddings", json=embed)
        audio_response = await client.post(
            "/v1/audio/transcriptions",
            files={"file": ("note.wav", audio, "audio/wav")},
            data={"model": "whisper-1"},
        )
    assert chat_response.status_code == 200
    assert embed_response.status_code != 429
    assert audio_response.status_code != 429
    assert spy.tokens[0] == 16 // 4
    assert spy.tokens[1] == 20 // 4
    assert spy.tokens[2] >= 1000
    assert spy.tokens[2] == len(audio) // 4


@pytest.mark.asyncio
async def test_transcription_tpm_denial_is_429_with_retry_after(settings):
    spy = _TokenSpy(default_tpm=10, retry_after_seconds=7)
    app = _app(settings, limiter=spy)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        denied = await client.post(
            "/v1/audio/transcriptions",
            files={"file": ("note.wav", b"z" * 4000, "audio/wav")},
            data={"model": "whisper-1"},
        )
    assert denied.status_code == 429
    assert denied.json()["error"]["type"] == "rate_limit_error"
    assert denied.headers["retry-after"] == "7"
    assert spy.tokens[0] >= 1000


@pytest.mark.asyncio
async def test_translation_tpm_counts_file_bytes_like_transcription(settings):
    """Multipart translations charge len(file)//4 the same as transcriptions (#796)."""
    spy = _TokenSpy(default_tpm=1_000_000)
    app = _app(settings, limiter=spy)
    audio = b"y" * 4000
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/audio/translations",
            files={"file": ("note.wav", audio, "audio/wav")},
            data={"model": "whisper-1"},
        )
    assert response.status_code != 429
    assert spy.tokens[0] == len(audio) // 4


@pytest.mark.asyncio
async def test_translation_tpm_denial_is_429_with_retry_after(settings):
    spy = _TokenSpy(default_tpm=10, retry_after_seconds=9)
    app = _app(settings, limiter=spy)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        denied = await client.post(
            "/v1/audio/translations",
            files={"file": ("note.wav", b"z" * 4000, "audio/wav")},
            data={"model": "whisper-1"},
        )
    assert denied.status_code == 429
    assert denied.json()["error"]["type"] == "rate_limit_error"
    assert denied.headers["retry-after"] == "9"
    assert spy.tokens[0] >= 1000


def test_team_rpd_gauge_decreases_and_rpm_stays_independent(monkeypatch):
    from types import SimpleNamespace

    monkeypatch.setattr("daari.auth.rate_limit.time.time", lambda: 1_700_000_030.0)
    limiter = RateLimiter(MemoryCounterBackend())
    team = SimpleNamespace(team_id="t1", name="eng", rpm=4, tpm=0, rpd=3)
    before = {row["kind"]: row for row in limiter.team_rate_gauges([team])}
    assert before["rpm"]["remaining"] == 4
    assert before["rpd"]["remaining"] == 3
    assert before["rpd"]["limit"] == 3
    assert "tpm" not in before
    limiter.check(key_id="a", model="m", tokens=1, team_id="t1", team_rpm=4, team_rpd=3)
    after = {row["kind"]: row for row in limiter.team_rate_gauges([team])}
    assert after["rpm"]["remaining"] == 3
    assert after["rpd"]["remaining"] == 2
    unlimited = SimpleNamespace(team_id="t2", name="ops", rpm=0, tpm=0, rpd=0)
    assert limiter.team_rate_gauges([unlimited]) == []


def test_safe_methods_skip_body_buffer_helper():
    from daari.auth.rate_limit import should_buffer_body_for_rate_limit

    assert should_buffer_body_for_rate_limit("GET") is False
    assert should_buffer_body_for_rate_limit("head") is False
    assert should_buffer_body_for_rate_limit("OPTIONS") is False
    assert should_buffer_body_for_rate_limit("POST") is True
    assert should_buffer_body_for_rate_limit("PUT") is True


@pytest.mark.asyncio
async def test_get_does_not_call_request_body(settings, monkeypatch):
    """Rate-limit middleware must not buffer bodies on safe methods (#939)."""
    settings.rate_limit.tpm = 1  # would 429 if a chat-sized body were estimated
    app = _app(settings)
    body_calls = {"n": 0}
    from starlette.requests import Request

    original = Request.body

    async def spy(self):
        body_calls["n"] += 1
        return await original(self)

    monkeypatch.setattr(Request, "body", spy)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/v1/models")
    assert response.status_code == 200
    assert body_calls["n"] == 0


@pytest.mark.asyncio
async def test_post_still_estimates_tokens_for_tpm(settings):
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
