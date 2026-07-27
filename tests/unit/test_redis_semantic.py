"""Unit tests for Redis L1 semantic cache (issue #135) — verification pass 1/3."""

from __future__ import annotations

import pytest

from daari.cache.redis_semantic import RedisSemanticCache
from daari.gateway.internal import DaariMeta, InternalRequest, InternalResponse, Message


class FakeRedis:
    def __init__(self) -> None:
        self.data: dict[str, str] = {}

    def get(self, key: str):
        return self.data.get(key)

    def set(self, key: str, value: str, ex: int | None = None):
        self.data[key] = value

    def delete(self, key: str):
        self.data.pop(key, None)


class FixedEmbedder:
    def __init__(self, vector: list[float] | None = None) -> None:
        self.vector = vector or [1.0, 0.0, 0.0]

    async def embed(self, text: str) -> list[float] | None:
        if not text.strip():
            return None
        return list(self.vector)


def _req(text: str = "explain caching") -> InternalRequest:
    return InternalRequest(messages=[Message(role="user", content=text)], model="daari")


def _resp(text: str = "cached answer") -> InternalResponse:
    return InternalResponse(
        content=text,
        model="m",
        daari_meta=DaariMeta(tier="L3", executor="ollama", provider_id="o", latency_ms=1),
    )


@pytest.mark.asyncio
async def test_redis_l1_round_trip_shared_key():
    client = FakeRedis()
    embedder = FixedEmbedder([1.0, 0.0, 0.0])
    writer = RedisSemanticCache(
        "redis://test",
        embedder,
        client=client,
        similarity_threshold=0.9,
    )
    await writer.put(_req("hello world"), _resp("from redis l1"))

    reader = RedisSemanticCache(
        "redis://test",
        embedder,
        client=client,
        similarity_threshold=0.9,
    )
    hit, score = await reader.get(_req("hello world"))
    assert hit is not None
    assert hit.content == "from redis l1"
    assert score is not None and score >= 0.9
    assert "daari:l1:entries" in client.data


@pytest.mark.asyncio
async def test_redis_l1_miss_below_threshold():
    client = FakeRedis()
    cache = RedisSemanticCache(
        "redis://test",
        FixedEmbedder([1.0, 0.0, 0.0]),
        client=client,
        similarity_threshold=0.99,
    )
    await cache.put(_req("alpha"), _resp("a"))
    # Orthogonal embedding → low cosine
    cache.embedder = FixedEmbedder([0.0, 1.0, 0.0])  # type: ignore[assignment]
    hit, score = await cache.get(_req("beta"))
    assert hit is None
    assert score is None or score < 0.99


@pytest.mark.asyncio
async def test_redis_l1_respects_ttl():
    client = FakeRedis()
    clock = {"t": 1000.0}
    cache = RedisSemanticCache(
        "redis://test",
        FixedEmbedder(),
        client=client,
        ttl_seconds=10,
        clock=lambda: clock["t"],
        similarity_threshold=0.5,
    )
    await cache.put(_req(), _resp())
    clock["t"] = 1011.0
    hit, _ = await cache.get(_req())
    assert hit is None


def test_missing_redis_package_message(monkeypatch):
    cache = RedisSemanticCache("redis://test", FixedEmbedder())
    import builtins

    real_import = builtins.__import__

    def blocked(name, *args, **kwargs):
        if name == "redis" or name.startswith("redis."):
            raise ImportError("no redis")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", blocked)
    with pytest.raises(RuntimeError, match="pip install"):
        cache._load_entries()
