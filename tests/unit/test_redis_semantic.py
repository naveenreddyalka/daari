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


class WatchError(Exception):
    """Stand-in for redis.WatchError — no redis package required."""


class ContendingRedis:
    """GET/SET plus WATCH/MULTI so a write between GET and EXEC is visible."""

    def __init__(self) -> None:
        self.data: dict[str, str] = {}
        self.on_get: object | None = None
        self.sets = 0

    def get(self, key: str):
        snapshot = self.data.get(key)
        hook = self.on_get
        if hook is not None:
            self.on_get = None
            hook()
        return snapshot

    def set(self, key: str, value: str, ex: int | None = None):
        self.sets += 1
        self.data[key] = value

    def pipeline(self):
        return _ContendingPipeline(self)


class _ContendingPipeline:
    def __init__(self, store: ContendingRedis) -> None:
        self.store = store
        self._watched: str | None = None
        self._snapshot: str | None = None
        self._ops: list[tuple] = []
        self._multi = False

    def watch(self, key: str):
        self._watched = key
        self._snapshot = self.store.data.get(key)

    def get(self, key: str):
        return self.store.get(key)

    def multi(self):
        self._multi = True

    def set(self, key: str, value: str, ex: int | None = None):
        self._ops.append((key, value, ex))

    def execute(self):
        if self._watched is not None and self.store.data.get(self._watched) != self._snapshot:
            raise WatchError("key changed")
        for key, value, ex in self._ops:
            self.store.set(key, value, ex)
        self._ops.clear()
        return [True]

    def reset(self):
        self._ops.clear()
        self._multi = False

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.reset()


@pytest.mark.asyncio
async def test_interleaved_puts_preserve_both_entries():
    """Replica B writes between A's GET and SET — both entries must survive (#150)."""
    client = ContendingRedis()
    embedder = FixedEmbedder([1.0, 0.0, 0.0])
    replica_a = RedisSemanticCache(
        "redis://test", embedder, client=client, similarity_threshold=0.5
    )

    def inject_b() -> None:
        client.on_get = None
        # Completed replica-B write against the same list key.
        import json

        client.data["daari:l1:entries"] = json.dumps(
            [
                {
                    "context_key": "other",
                    "embedding": [0.0, 1.0, 0.0],
                    "prompt_text": "from-b",
                    "response_json": _resp("b").model_dump_json(),
                    "created_at": 1.0,
                    "category": "unknown",
                    "answer_hash": "b",
                }
            ]
        )

    client.on_get = inject_b
    await replica_a.put(_req("from-a"), _resp("a"))
    texts = {entry.get("prompt_text") for entry in replica_a._load_entries()}
    assert "from-b" in texts
    assert any(text and "from-a" in text for text in texts)


@pytest.mark.asyncio
async def test_max_entries_holds_under_contended_write():
    client = ContendingRedis()
    cache = RedisSemanticCache(
        "redis://test",
        FixedEmbedder(),
        client=client,
        max_entries=2,
        similarity_threshold=0.5,
    )
    await cache.put(_req("one"), _resp("1"))
    await cache.put(_req("two"), _resp("2"))

    def inject_third() -> None:
        import json

        entries = json.loads(client.data["daari:l1:entries"])
        entries.append(
            {
                "context_key": "x",
                "embedding": [1.0, 0.0, 0.0],
                "prompt_text": "injected",
                "response_json": _resp("i").model_dump_json(),
                "created_at": 1.0,
                "category": "unknown",
                "answer_hash": "i",
            }
        )
        client.data["daari:l1:entries"] = json.dumps(entries)

    client.on_get = inject_third
    await cache.put(_req("three"), _resp("3"))
    assert len(cache._load_entries()) <= 2


@pytest.mark.asyncio
async def test_contended_write_does_not_raise():
    client = ContendingRedis()
    cache = RedisSemanticCache("redis://test", FixedEmbedder(), client=client)

    def always_change() -> None:
        client.on_get = always_change
        client.data["daari:l1:entries"] = "[]"

    client.on_get = always_change
    await cache.put(_req("keep-going"), _resp("ok"))
    assert cache._load_entries()  # last attempt still persisted


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
