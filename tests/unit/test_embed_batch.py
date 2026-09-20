"""Batch Ollama embed calls for list inputs (issue #766)."""

from __future__ import annotations

import json

import httpx
import pytest

from daari.cache.semantic import OllamaEmbedder
from daari.gateway.embeddings_api import compute_embeddings, embedding_cache_request
from daari.gateway.internal import DaariMeta, InternalResponse
from daari.router.router import AppContext


def _batch_embedder(
    requests: list[dict],
    *,
    embed_status: int = 200,
    cache_size: int = 512,
):
    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        path = request.url.path
        requests.append({"path": path, "payload": payload})
        if path.endswith("/api/embed"):
            if embed_status != 200:
                return httpx.Response(embed_status)
            texts = payload["input"]
            if isinstance(texts, str):
                texts = [texts]
            return httpx.Response(
                200,
                json={
                    "embeddings": [
                        [1.0, float(len(text)), float(index)]
                        for index, text in enumerate(texts)
                    ]
                },
            )
        if path.endswith("/api/embeddings"):
            text = payload["prompt"]
            return httpx.Response(200, json={"embedding": [2.0, float(len(text))]})
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    return OllamaEmbedder(
        "http://test", "nomic-embed-text", cache_size=cache_size, transport=transport
    )


@pytest.mark.asyncio
async def test_embed_many_one_http_for_two_misses():
    requests: list[dict] = []
    embedder = _batch_embedder(requests)

    vectors = await embedder.embed_many(["alpha", "beta"])

    assert vectors == [[1.0, 5.0, 0.0], [1.0, 4.0, 1.0]]
    assert len(requests) == 1
    assert requests[0]["path"].endswith("/api/embed")
    assert requests[0]["payload"]["input"] == ["alpha", "beta"]


@pytest.mark.asyncio
async def test_embed_many_zero_http_when_both_cached():
    requests: list[dict] = []
    embedder = _batch_embedder(requests)

    await embedder.embed_many(["alpha", "beta"])
    requests.clear()
    vectors = await embedder.embed_many(["alpha", "beta"])

    assert vectors == [[1.0, 5.0, 0.0], [1.0, 4.0, 1.0]]
    assert requests == []


@pytest.mark.asyncio
async def test_embed_single_still_returns_one_vector():
    requests: list[dict] = []
    embedder = _batch_embedder(requests)

    vector = await embedder.embed("solo")

    assert vector == [1.0, 4.0, 0.0]
    assert len(requests) == 1
    assert requests[0]["payload"]["input"] == ["solo"]


@pytest.mark.asyncio
async def test_embed_many_falls_back_on_404():
    requests: list[dict] = []
    embedder = _batch_embedder(requests, embed_status=404)

    vectors = await embedder.embed_many(["alpha", "beta"])

    assert vectors == [[2.0, 5.0], [2.0, 4.0]]
    assert [r["path"] for r in requests] == [
        "/api/embed",
        "/api/embeddings",
        "/api/embeddings",
    ]
    assert requests[1]["payload"]["prompt"] == "alpha"
    assert requests[2]["payload"]["prompt"] == "beta"


@pytest.mark.asyncio
async def test_compute_embeddings_batches_l0_misses_only(settings):
    requests: list[dict] = []
    embedder = _batch_embedder(requests, cache_size=0)
    settings.cache.l1.enabled = True
    ctx = AppContext.from_settings(settings)
    ctx.router.semantic_cache.embedder = embedder
    model = settings.cache.l1.embedding_model

    ctx.router.cache.put(
        embedding_cache_request(model, "cached"),
        InternalResponse(
            content=json.dumps([9.0, 9.0]),
            model=model,
            daari_meta=DaariMeta(
                tier="embed",
                cache_hit=True,
                executor="ollama",
                provider_id="ollama",
                model=model,
            ),
        ),
    )

    vectors = await compute_embeddings(ctx, ["cached", "miss-a", "miss-b"], model=model)

    assert vectors[0] == [9.0, 9.0]
    assert vectors[1] == [1.0, 6.0, 0.0]
    assert vectors[2] == [1.0, 6.0, 1.0]
    assert len(requests) == 1
    assert requests[0]["payload"]["input"] == ["miss-a", "miss-b"]
