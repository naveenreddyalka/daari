"""LRU memoization in front of OllamaEmbedder (issue #45)."""

from __future__ import annotations

import json

import httpx
import pytest

from daari.cache.semantic import OllamaEmbedder
from daari.config.settings import Settings


def _embedder(calls: list[str], *, cache_size: int = 512, fail_texts: set[str] | None = None):
    fail = fail_texts or set()

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        calls.append(payload["prompt"])
        if payload["prompt"] in fail:
            return httpx.Response(500)
        return httpx.Response(200, json={"embedding": [1.0, float(len(payload["prompt"]))]})

    transport = httpx.MockTransport(handler)
    embedder = OllamaEmbedder(
        "http://test", "nomic-embed-text", cache_size=cache_size, transport=transport
    )
    return embedder


@pytest.mark.asyncio
async def test_repeat_embed_hits_cache():
    calls: list[str] = []
    embedder = _embedder(calls)

    first = await embedder.embed("hello world")
    second = await embedder.embed("hello world")

    assert first == second
    assert calls == ["hello world"], "second embed must not make an HTTP call"


@pytest.mark.asyncio
async def test_distinct_texts_miss():
    calls: list[str] = []
    embedder = _embedder(calls)

    await embedder.embed("alpha")
    await embedder.embed("beta")

    assert calls == ["alpha", "beta"]


@pytest.mark.asyncio
async def test_failures_not_cached():
    calls: list[str] = []
    embedder = _embedder(calls, fail_texts={"flaky"})

    assert await embedder.embed("flaky") is None
    assert await embedder.embed("flaky") is None

    assert calls == ["flaky", "flaky"], "None results must retry, not be cached"


@pytest.mark.asyncio
async def test_lru_eviction():
    calls: list[str] = []
    embedder = _embedder(calls, cache_size=2)

    await embedder.embed("one")
    await embedder.embed("two")
    await embedder.embed("three")  # evicts "one"
    await embedder.embed("one")

    assert calls == ["one", "two", "three", "one"]


@pytest.mark.asyncio
async def test_zero_size_disables_cache():
    calls: list[str] = []
    embedder = _embedder(calls, cache_size=0)

    await embedder.embed("same")
    await embedder.embed("same")

    assert calls == ["same", "same"]


def test_settings_expose_embed_cache_size():
    settings = Settings.model_validate({})
    assert settings.cache.l1.embed_cache_size == 512
