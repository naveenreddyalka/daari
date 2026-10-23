"""Fleet-shared systemone breaker state via Redis (#1868)."""

from __future__ import annotations

import json

import pytest

from daari.gateway import systemone


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
def _clean_breakers():
    systemone.reset_systemone_breakers()
    systemone.set_systemone_breaker_redis(None)
    yield
    systemone.reset_systemone_breakers()
    systemone.set_systemone_breaker_redis(None)


def test_shared_trip_visible_on_fresh_local_dict():
    """Pod A trips; pod B (empty local dict, same Redis) sees open (#1868)."""
    redis = FakeRedis()
    systemone.set_systemone_breaker_redis(redis)
    base = "http://vllm.local:8000"
    breaker = systemone.breaker_for(base)
    breaker.failure_threshold = 1
    breaker.cooldown_seconds = 60.0
    systemone._note_failure(base)
    assert systemone.breaker_snapshot()[0]["state"] == "open"

    # Simulate another replica: wipe process-local state, keep Redis.
    systemone._breakers.clear()
    systemone._breaker_rejects.clear()
    assert systemone._breakers == {}

    rows = systemone.breaker_snapshot()
    assert len(rows) == 1
    assert rows[0]["base"] == base
    assert rows[0]["state"] == "open"

    with pytest.raises(systemone.SystemOneCircuitOpen):
        systemone._reject_if_open(base)


def test_fleet_wide_reset_clears_shared_state():
    redis = FakeRedis()
    systemone.set_systemone_breaker_redis(redis)
    base = "http://vllm.local:8000"
    breaker = systemone.breaker_for(base)
    breaker.failure_threshold = 1
    breaker.cooldown_seconds = 60.0
    systemone._note_failure(base)
    assert any(k.startswith("daari:systemone:breaker:") for k in redis.store)

    after = systemone.close_systemone_breakers()
    assert all(row["state"] == "closed" for row in after)
    assert not any(k.startswith("daari:systemone:breaker:") for k in redis.store)
    assert systemone.systemone_breaker_backend() == "redis"

    systemone._breakers.clear()
    assert systemone.breaker_snapshot() == []
    # Probe allowed after fleet reset
    systemone._reject_if_open(base)


def test_redis_outage_fail_open_uses_local():
    redis = BoomRedis()
    systemone.set_systemone_breaker_redis(redis)
    base = "http://vllm.local:8000"
    # Local closed + Redis boom → allow (fail-open)
    systemone._reject_if_open(base)

    breaker = systemone.breaker_for(base)
    breaker.failure_threshold = 1
    breaker.cooldown_seconds = 60.0
    systemone._note_failure(base)  # local trip; Redis write fails open
    assert breaker.state == "open"
    with pytest.raises(systemone.SystemOneCircuitOpen):
        systemone._reject_if_open(base)


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
    systemone.configure_systemone_breaker_store(Settings())
    assert systemone.systemone_breaker_backend() == "redis"
    assert systemone._breaker_redis is redis
