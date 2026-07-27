"""Integration: Redis L1 shared across two AppContext-style caches (issue #135).

Verification pass 2/3 — ASGI gateway with FakeRedis-backed L1.
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from daari.cache.redis_semantic import RedisSemanticCache
from daari.gateway.internal import DaariMeta, InternalRequest, InternalResponse
from daari.router.router import AppContext
from daari.server.app import create_app
from tests.conftest import META_HEADERS


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
    async def embed(self, text: str) -> list[float] | None:
        # Same vector for any non-empty text → paraphrase always hits.
        return [1.0, 0.0, 0.0] if text.strip() else None


@pytest.mark.asyncio
async def test_gateway_l1_hit_via_shared_redis(settings, monkeypatch):
    shared = FakeRedis()
    settings.cache.backend = "redis"
    settings.cache.l0.enabled = False  # force L1 path (skip exact)
    settings.cache.l1.enabled = True
    settings.cache.l1.similarity_threshold = 0.5

    app = create_app(settings)
    ctx = AppContext.from_settings(settings)
    # Swap L1 for a FakeRedis-backed instance with deterministic embeddings.
    ctx.semantic_cache = RedisSemanticCache(
        settings.cache.redis_url,
        FixedEmbedder(),
        client=shared,
        enabled=True,
        similarity_threshold=0.5,
        normalize_inputs=False,
    )
    ctx.router.semantic_cache = ctx.semantic_cache
    app.state.ctx = ctx

    calls = {"n": 0}

    async def fake_execute(request: InternalRequest) -> InternalResponse:
        calls["n"] += 1
        return InternalResponse(
            content="shared-l1-answer",
            model="llama3.2:3b",
            daari_meta=DaariMeta(
                tier="L3",
                executor="ollama",
                provider_id="ollama",
                latency_ms=5,
            ),
        )

    monkeypatch.setattr(ctx.router.ollama, "execute", fake_execute)
    monkeypatch.setattr(ctx.router.ollama_l3, "execute", fake_execute)
    monkeypatch.setattr(ctx.router.ollama_l4, "execute", fake_execute)
    monkeypatch.setattr(ctx.router.ollama_l5, "execute", fake_execute)

    payload_a = {
        "model": "daari",
        "messages": [{"role": "user", "content": "What is Redis L1 sharing?"}],
    }
    payload_b = {
        "model": "daari",
        "messages": [{"role": "user", "content": "Explain Redis L1 sharing please"}],
    }

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        first = await client.post("/v1/chat/completions", json=payload_a, headers=META_HEADERS)
        second = await client.post("/v1/chat/completions", json=payload_b, headers=META_HEADERS)

    assert first.status_code == 200
    assert first.json()["daari_meta"]["tier"] == "L3"
    assert second.status_code == 200
    assert second.json()["daari_meta"]["tier"] == "L1"
    assert second.json()["daari_meta"]["cache_hit"] is True
    assert "shared-l1-answer" in second.json()["choices"][0]["message"]["content"]
    assert calls["n"] == 1
    assert "daari:l1:entries" in shared.data
