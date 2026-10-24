"""Fleet-shared frontier / local / MCP circuit breakers via Redis (#1908)."""

from __future__ import annotations

import pytest

from daari.router import breaker_redis, circuit_breaker
from daari.router.circuit_breaker import CircuitBreaker


class FakeRedis:
    def __init__(self) -> None:
        self.store: dict[str, str] = {}
        self.ttls: dict[str, int] = {}

    def get(self, key: str) -> str | None:
        return self.store.get(key)

    def set(self, key: str, value: str, ex: int | None = None) -> bool:
        self.store[key] = value
        if ex is not None:
            self.ttls[key] = int(ex)
        return True

    def incr(self, key: str) -> int:
        cur = int(self.store.get(key) or 0) + 1
        self.store[key] = str(cur)
        return cur

    def expire(self, key: str, seconds: int) -> bool:
        self.ttls[key] = int(seconds)
        return True

    def delete(self, *keys: str) -> int:
        n = 0
        for key in keys:
            if key in self.store:
                del self.store[key]
                n += 1
            self.ttls.pop(key, None)
        return n

    def keys(self, pattern: str) -> list[str]:
        prefix = pattern.rstrip("*")
        return [k for k in self.store if k.startswith(prefix)]


class BoomRedis(FakeRedis):
    def get(self, key: str) -> str | None:
        raise ConnectionError("redis down")

    def set(self, key: str, value: str, ex: int | None = None) -> bool:
        raise ConnectionError("redis down")

    def incr(self, key: str) -> int:
        raise ConnectionError("redis down")

    def delete(self, *keys: str) -> int:
        raise ConnectionError("redis down")

    def keys(self, pattern: str) -> list[str]:
        raise ConnectionError("redis down")


@pytest.fixture(autouse=True)
def _clean_store():
    breaker_redis.set_breaker_redis(None)
    yield
    breaker_redis.set_breaker_redis(None)


def test_shared_open_visible_across_fresh_breaker():
    """Pod A trips; pod B (fresh local breaker, same Redis) sees open (#1908)."""
    redis = FakeRedis()
    breaker_redis.set_breaker_redis(redis)
    a = CircuitBreaker(
        failure_threshold=1,
        cooldown_seconds=60.0,
        share_key="frontier:openai",
    )
    a.record_failure()
    assert a.state == "open"
    assert any(k.startswith("daari:breaker:") for k in redis.store)

    b = CircuitBreaker(
        failure_threshold=1,
        cooldown_seconds=60.0,
        share_key="frontier:openai",
    )
    assert b.state == "open"
    assert b.allow() is False
    assert b.reject_count() >= 1


def test_local_families_share_same_prefix_shape():
    redis = FakeRedis()
    breaker_redis.set_breaker_redis(redis)
    for key in ("frontier:p1", "local:gpu-a", "mcp:tools"):
        cb = CircuitBreaker(failure_threshold=1, cooldown_seconds=60.0, share_key=key)
        cb.record_failure()
    keys = sorted(k for k in redis.store if k.startswith("daari:breaker:"))
    assert keys == [
        "daari:breaker:frontier:p1",
        "daari:breaker:local:gpu-a",
        "daari:breaker:mcp:tools",
    ]


def test_without_redis_process_local_unchanged():
    assert breaker_redis.breaker_redis_backend() == "local"
    a = CircuitBreaker(failure_threshold=1, cooldown_seconds=60.0, share_key="local:x")
    a.record_failure()
    assert a.state == "open"
    b = CircuitBreaker(failure_threshold=1, cooldown_seconds=60.0, share_key="local:x")
    assert b.state == "closed"
    assert b.allow() is True


def test_redis_outage_fail_open_uses_local():
    breaker_redis.set_breaker_redis(BoomRedis())
    # Local closed + Redis boom → allow (fail-open)
    closed = CircuitBreaker(
        failure_threshold=3, cooldown_seconds=60.0, share_key="mcp:srv"
    )
    assert closed.allow() is True

    open_local = CircuitBreaker(
        failure_threshold=1, cooldown_seconds=60.0, share_key="mcp:srv"
    )
    open_local.record_failure()  # local trip; Redis write fails open
    assert open_local.state == "open"
    assert open_local.allow() is False


def test_success_clears_shared_state():
    redis = FakeRedis()
    breaker_redis.set_breaker_redis(redis)
    a = CircuitBreaker(failure_threshold=1, cooldown_seconds=60.0, share_key="local:b1")
    a.record_failure()
    assert redis.store
    a.record_success()
    assert not any(k.startswith("daari:breaker:local:b1") for k in redis.store)
    b = CircuitBreaker(failure_threshold=1, cooldown_seconds=60.0, share_key="local:b1")
    assert b.state == "closed"
    assert b.allow() is True


def test_configure_from_settings_uses_redis_when_backend_redis(monkeypatch):
    redis = FakeRedis()

    class Cache:
        backend = "redis"
        redis_url = "redis://localhost:6379/0"
        redis_timeout_seconds = 1.0

    class Settings:
        cache = Cache()

    monkeypatch.setattr(
        "daari.cache.redis_client.connect_redis",
        lambda url, timeout_seconds=2.0: redis,
    )
    breaker_redis.configure_breaker_redis_store(Settings())
    assert breaker_redis.breaker_redis_backend() == "redis"
    assert circuit_breaker._breaker_store_client() is redis


def test_share_key_helpers_and_builders():
    assert breaker_redis.share_key_for("frontier", "openai") == "frontier:openai"
    assert breaker_redis.share_key_for("local", "gpu-a") == "local:gpu-a"
    assert breaker_redis.share_key_for("mcp", "tools") == "mcp:tools"

    from daari.router.local_pool import LocalBackendSlot

    slot = LocalBackendSlot(
        id="gpu-a",
        base_url="http://localhost:11434",
        breaker=CircuitBreaker(share_key=breaker_redis.share_key_for("local", "gpu-a")),
    )
    assert slot.breaker.share_key == "local:gpu-a"
