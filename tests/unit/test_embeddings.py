"""POST /v1/embeddings is a first-class surface (issue #163).

The embedder already runs in-process for L1. Apps that wanted a vector had to
point at a second host, which breaks the one-local-base-URL story.
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from daari.router.router import AppContext
from daari.server.app import create_app
from tests.conftest import META_HEADERS

VECTOR = [0.1, 0.2, 0.3, 0.4]


class RecordingEmbedder:
    def __init__(self, model: str = "nomic-embed-text"):
        self.model = model
        self.calls: list[tuple[str, str]] = []

    async def embed(self, text: str, *, model: str | None = None) -> list[float] | None:
        used = model or self.model
        self.calls.append((used, text))
        return list(VECTOR)

    async def embed_many(
        self, texts: list[str], *, model: str | None = None
    ) -> list[list[float] | None]:
        return [await self.embed(text, model=model) for text in texts]


def _app(settings, embedder):
    settings.cache.l1.enabled = True
    app = create_app(settings)
    ctx = AppContext.from_settings(settings)
    ctx.router.semantic_cache.embedder = embedder
    app.state.ctx = ctx
    return app


async def _post(app, body):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.post("/v1/embeddings", json=body, headers=META_HEADERS)


@pytest.mark.asyncio
async def test_a_string_input_returns_one_openai_shaped_item(settings):
    embedder = RecordingEmbedder()
    response = await _post(
        _app(settings, embedder), {"model": "nomic-embed-text", "input": "hello"}
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["object"] == "list"
    assert body["data"][0]["embedding"] == VECTOR
    assert body["data"][0]["index"] == 0
    assert embedder.calls == [("nomic-embed-text", "hello")]


@pytest.mark.asyncio
async def test_a_batch_input_preserves_order(settings):
    embedder = RecordingEmbedder()
    response = await _post(
        _app(settings, embedder),
        {"model": "nomic-embed-text", "input": ["one", "two"]},
    )

    assert [item["index"] for item in response.json()["data"]] == [0, 1]
    assert [text for _, text in embedder.calls] == ["one", "two"]


@pytest.mark.asyncio
async def test_daari_alias_uses_the_configured_embedder(settings):
    embedder = RecordingEmbedder()
    response = await _post(_app(settings, embedder), {"model": "daari", "input": "hello"})

    assert response.status_code == 200
    assert embedder.calls[0][0] == settings.cache.l1.embedding_model


@pytest.mark.asyncio
async def test_an_unknown_model_is_400(settings):
    embedder = RecordingEmbedder()
    response = await _post(_app(settings, embedder), {"model": "totally-unknown", "input": "hello"})

    assert response.status_code == 400
    assert embedder.calls == []


@pytest.mark.asyncio
async def test_identical_inputs_hit_l0(settings):
    embedder = RecordingEmbedder()
    app = _app(settings, embedder)
    first = await _post(app, {"model": "nomic-embed-text", "input": "hello"})
    second = await _post(app, {"model": "nomic-embed-text", "input": "hello"})

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["data"][0]["embedding"] == second.json()["data"][0]["embedding"]
    assert len(embedder.calls) == 1, "the second call must be served from cache"


@pytest.mark.asyncio
async def test_embeddings_are_on_the_models_list(settings):
    app = _app(settings, RecordingEmbedder())
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/v1/models", headers=META_HEADERS)

    ids = [item["id"] for item in response.json()["data"]]
    assert settings.cache.l1.embedding_model in ids


@pytest.mark.asyncio
async def test_metrics_record_an_embed_tier(settings):
    embedder = RecordingEmbedder()
    app = _app(settings, embedder)
    await _post(app, {"model": "nomic-embed-text", "input": "hello"})

    snapshot = app.state.ctx.metrics.snapshot()
    assert snapshot["embed"]["count"] >= 1


@pytest.mark.asyncio
async def test_embed_cache_miss_records_positive_latency(settings):
    import asyncio

    class SlowEmbedder(RecordingEmbedder):
        async def embed(self, text: str, *, model: str | None = None) -> list[float] | None:
            await asyncio.sleep(0.02)
            return await super().embed(text, model=model)

    app = _app(settings, SlowEmbedder())
    response = await _post(app, {"model": "nomic-embed-text", "input": "hello"})
    assert response.status_code == 200, response.text
    snapshot = app.state.ctx.metrics.snapshot(include_histograms=True)
    embed = snapshot["tiers"]["embed"]
    assert embed["count"] >= 1
    assert embed["total_latency_ms"] > 0
    assert sum(embed["latency_buckets"].values()) > 0


def _spend_rows(app):
    ledger = app.state.ctx.router.spend_ledger
    return list(ledger.iter_rows(since="2000-01-01T00:00:00+00:00"))


@pytest.mark.asyncio
async def test_embeddings_spend_row_keeps_key_and_team(settings, tmp_path):
    """Chargeback export attributes embedding calls to the virtual key (#755)."""
    from daari.auth.virtual_keys import VirtualKeyStore

    settings.usage.spend.enabled = True
    settings.usage.spend.path = str(tmp_path / "spend.sqlite3")
    settings.server.api_key = "master"
    settings.server.virtual_keys.path = str(tmp_path / "vk.sqlite3")
    store = VirtualKeyStore(settings.virtual_keys_path)
    key = store.create("bot", client_id="client-bot", team="eng")
    embedder = RecordingEmbedder()
    app = _app(settings, embedder)
    app.state.virtual_key_store = store
    app.state.ctx.virtual_key_store = store

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/v1/embeddings",
            json={"model": "nomic-embed-text", "input": "hello"},
            headers={"Authorization": f"Bearer {key.plaintext}"},
        )
    assert response.status_code == 200, response.text
    rows = _spend_rows(app)
    assert len(rows) == 1
    assert rows[0]["tier"] == "embed"
    assert rows[0]["key_id"] == key.key.key_id
    assert rows[0]["team_id"] == key.key.team_id
    assert rows[0]["model"] == "nomic-embed-text"


@pytest.mark.asyncio
async def test_unknown_embedding_model_does_not_write_spend(settings, tmp_path):
    settings.usage.spend.enabled = True
    settings.usage.spend.path = str(tmp_path / "spend.sqlite3")
    embedder = RecordingEmbedder()
    app = _app(settings, embedder)
    response = await _post(app, {"model": "totally-unknown", "input": "hello"})
    assert response.status_code == 400
    assert _spend_rows(app) == []


@pytest.mark.asyncio
async def test_scoped_keys_do_not_share_embedding_l0(settings, tmp_path):
    """cache_scope=key isolates embed vectors across virtual keys (#841)."""
    from daari.auth.virtual_keys import VirtualKeyStore
    from daari.cache.exact import ExactCache, cache_key
    from daari.gateway.embeddings_api import embedding_cache_request
    from daari.gateway.internal import RequestMeta
    from daari.server.auth import apply_auth_claims_to_meta, resolve_auth

    settings.server.api_key = "master"
    settings.server.virtual_keys.path = str(tmp_path / "vk.sqlite3")
    settings.cache.l0.enabled = True
    settings.cache.l0.path = str(tmp_path / "l0")
    store = VirtualKeyStore(settings.virtual_keys_path)
    left = store.create("left", client_id="left", cache_scope="key")
    right = store.create("right", client_id="right", cache_scope="key")
    embedder = RecordingEmbedder()
    app = _app(settings, embedder)
    app.state.virtual_key_store = store
    app.state.ctx.virtual_key_store = store

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        first = await client.post(
            "/v1/embeddings",
            json={"model": "nomic-embed-text", "input": "same text"},
            headers={"Authorization": f"Bearer {left.plaintext}"},
        )
        second = await client.post(
            "/v1/embeddings",
            json={"model": "nomic-embed-text", "input": "same text"},
            headers={"Authorization": f"Bearer {right.plaintext}"},
        )
        again = await client.post(
            "/v1/embeddings",
            json={"model": "nomic-embed-text", "input": "same text"},
            headers={"Authorization": f"Bearer {left.plaintext}"},
        )
        ollama = await client.post(
            "/api/embed",
            json={"model": "nomic-embed-text", "input": "same text"},
            headers={"Authorization": f"Bearer {right.plaintext}"},
        )
    assert first.status_code == 200 and second.status_code == 200
    assert again.status_code == 200 and ollama.status_code == 200
    # left miss, right miss, left hit, right /api/embed hit → 2 embedder calls
    assert len(embedder.calls) == 2
    assert [text for _, text in embedder.calls] == ["same text", "same text"]

    left_meta = RequestMeta()
    apply_auth_claims_to_meta(left_meta, resolve_auth(left.plaintext, master_key="master", store=store))
    right_meta = RequestMeta()
    apply_auth_claims_to_meta(right_meta, resolve_auth(right.plaintext, master_key="master", store=store))
    assert left_meta.cache_scope == "key" and right_meta.cache_scope == "key"
    assert cache_key(embedding_cache_request("nomic-embed-text", "same text", meta=left_meta)) != cache_key(
        embedding_cache_request("nomic-embed-text", "same text", meta=right_meta)
    )

    cache = ExactCache(str(settings.l0_cache_path), enabled=True)
    assert cache.invalidate(key_id=left.key.key_id) == 1
    assert cache.get(embedding_cache_request("nomic-embed-text", "same text", meta=left_meta)) is None
    assert cache.get(embedding_cache_request("nomic-embed-text", "same text", meta=right_meta)) is not None


@pytest.mark.asyncio
async def test_global_and_master_embed_cache_unchanged(settings, tmp_path):
    settings.server.api_key = "master"
    settings.server.virtual_keys.path = str(tmp_path / "vk.sqlite3")
    settings.cache.l0.enabled = True
    from daari.auth.virtual_keys import VirtualKeyStore

    store = VirtualKeyStore(settings.virtual_keys_path)
    open_key = store.create("open", client_id="open")  # global scope
    embedder = RecordingEmbedder()
    app = _app(settings, embedder)
    app.state.virtual_key_store = store
    app.state.ctx.virtual_key_store = store
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        a = await client.post(
            "/v1/embeddings",
            json={"model": "nomic-embed-text", "input": "shared"},
            headers={"Authorization": f"Bearer {open_key.plaintext}"},
        )
        b = await client.post(
            "/v1/embeddings",
            json={"model": "nomic-embed-text", "input": "shared"},
            headers={"Authorization": "Bearer master"},
        )
    assert a.status_code == 200 and b.status_code == 200
    assert len(embedder.calls) == 1
