"""Shared Redis session pins + cost-avoided rollup across replicas (#482)."""

from __future__ import annotations

import pytest

from daari.gateway.cost_headers import SessionAvoidedStore
from daari.router.session_affinity import ProfilePinStore, SessionPinStore


class FakeRedis:
    """Minimal get/set/expire/incrbyfloat stand-in shared by two store instances."""

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

    def incrbyfloat(self, key: str, amount: float) -> float:
        cur = float(self.store.get(key) or 0.0) + float(amount)
        self.store[key] = str(cur)
        return cur

    def expire(self, key: str, seconds: int) -> bool:
        self.ttls[key] = int(seconds)
        return True


class BoomRedis(FakeRedis):
    def get(self, key: str) -> str | None:
        raise ConnectionError("redis down")

    def set(self, key: str, value: str, ex: int | None = None) -> bool:
        raise ConnectionError("redis down")

    def incrbyfloat(self, key: str, amount: float) -> float:
        raise ConnectionError("redis down")


def test_two_replicas_share_session_pins():
    redis = FakeRedis()
    a = SessionPinStore(ttl_seconds=60, redis_client=redis)
    b = SessionPinStore(ttl_seconds=60, redis_client=redis)
    a.put("session:agent-1", tier="L4", model="llama3.1:8b", prefix_hash="abc")
    pin = b.get("session:agent-1")
    assert pin is not None
    assert pin.tier == "L4"
    assert pin.model == "llama3.1:8b"
    assert pin.prefix_hash == "abc"
    assert redis.ttls[a._redis_key("session:agent-1")] == 60


def test_two_replicas_share_profile_pins():
    redis = FakeRedis()
    a = ProfilePinStore(ttl_seconds=60, redis_client=redis)
    b = ProfilePinStore(ttl_seconds=60, redis_client=redis)
    a.put(
        "session:agent-1",
        category="coding",
        complexity="medium",
        prefix_hash="abc",
    )
    pin = b.get("session:agent-1")
    assert pin is not None
    assert pin.category == "coding"
    assert pin.complexity == "medium"
    assert pin.prefix_hash == "abc"
    assert redis.ttls[a._redis_key("session:agent-1")] == 60


def test_two_replicas_share_session_cost_avoided():
    redis = FakeRedis()
    a = SessionAvoidedStore(ttl_seconds=60, redis_client=redis)
    b = SessionAvoidedStore(ttl_seconds=60, redis_client=redis)
    assert a.add("sess-1", 0.10) == pytest.approx(0.10)
    assert b.add("sess-1", 0.05) == pytest.approx(0.15)
    assert a.total("sess-1") == pytest.approx(0.15)
    assert b.total("sess-1") == pytest.approx(0.15)


def test_redis_errors_fail_open_to_memory():
    redis = BoomRedis()
    pins = SessionPinStore(ttl_seconds=60, redis_client=redis)
    profiles = ProfilePinStore(ttl_seconds=60, redis_client=redis)
    savings = SessionAvoidedStore(ttl_seconds=60, redis_client=redis)
    pins.put("session:x", tier="L3", model="m", prefix_hash="h")
    profiles.put("session:x", category="coding", complexity="low", prefix_hash="h")
    assert pins.get("session:x") is not None
    assert pins.get("session:x").tier == "L3"
    assert profiles.get("session:x") is not None
    assert profiles.get("session:x").category == "coding"
    assert savings.add("s1", 1.0) == pytest.approx(1.0)
    assert savings.total("s1") == pytest.approx(1.0)
    assert pins._degraded is True
    assert profiles._degraded is True
    assert savings._degraded is True


def test_shared_savings_surface_in_cost_headers():
    from daari.config.settings import Settings
    from daari.gateway.cost_headers import SESSION_COST_AVOIDED_HEADER, response_cost_headers
    from daari.gateway.internal import DaariMeta

    redis = FakeRedis()
    savings = SessionAvoidedStore(ttl_seconds=60, redis_client=redis)
    peer = SessionAvoidedStore(ttl_seconds=60, redis_client=redis)
    peer.add("agent-loop", 0.25)
    meta = DaariMeta(tier="L3", executor="ollama")
    headers = response_cost_headers(
        meta,
        Settings.model_validate({"usage": {"frontier_price_per_1k_tokens": 0.002}}),
        prompt_chars=0,
        completion_chars=0,
        session_id="agent-loop",
        savings=savings,
    )
    assert float(headers[SESSION_COST_AVOIDED_HEADER]) == pytest.approx(0.25)
