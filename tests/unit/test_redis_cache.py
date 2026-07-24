"""F4 Redis L0 cache backend (issue #112)."""

from __future__ import annotations


import pytest

from daari.cache.redis_exact import RedisExactCache
from daari.config.settings import Settings
from daari.gateway.internal import DaariMeta, InternalRequest, InternalResponse, Message
from daari.router.router import _build_l0_cache


class FakeRedis:
    def __init__(self) -> None:
        self.data: dict[str, str] = {}

    def get(self, key: str):
        return self.data.get(key)

    def set(self, key: str, value: str, ex: int | None = None):
        self.data[key] = value

    def delete(self, key: str):
        self.data.pop(key, None)


def _req(text: str = "hello") -> InternalRequest:
    return InternalRequest(messages=[Message(role="user", content=text)], model="daari")


def _resp(text: str = "world") -> InternalResponse:
    return InternalResponse(
        content=text,
        model="m",
        daari_meta=DaariMeta(tier="L3", executor="ollama", provider_id="o", latency_ms=1),
    )


def test_redis_round_trip():
    client = FakeRedis()
    cache = RedisExactCache("redis://test", client=client, enabled=True)
    cache.put(_req(), _resp("cached"))
    hit = cache.get(_req())
    assert hit is not None and hit.content == "cached"
    assert any(k.startswith("daari:l0:") for k in client.data)


def test_redis_respects_ttl_expiry():
    client = FakeRedis()
    clock = {"t": 1000.0}
    cache = RedisExactCache(
        "redis://test", client=client, enabled=True, ttl_seconds=10, clock=lambda: clock["t"]
    )
    cache.put(_req(), _resp())
    clock["t"] = 1011.0
    assert cache.get(_req()) is None


def test_build_l0_cache_selects_redis(tmp_path):
    settings = Settings()
    settings.cache.backend = "redis"
    settings.cache.redis_url = "redis://example:6379/0"
    cache = _build_l0_cache(settings, tmp_path / "l0")
    assert isinstance(cache, RedisExactCache)


def test_missing_redis_package_message(monkeypatch):
    cache = RedisExactCache("redis://test", enabled=True)

    import builtins

    real_import = builtins.__import__

    def blocked(name, *args, **kwargs):
        if name == "redis" or name.startswith("redis."):
            raise ImportError("no redis")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", blocked)
    with pytest.raises(RuntimeError, match="pip install"):
        cache.put(_req(), _resp())
