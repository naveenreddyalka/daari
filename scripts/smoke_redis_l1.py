#!/usr/bin/env python3
"""Live/smoke verification for Redis L1 (issue #135) — pass 3/3.

Two modes:
1) In-process FakeRedis (no Redis/Ollama required) — default
2) Optional real Redis: REDIS_URL=redis://127.0.0.1:6379/0

Hits the FastAPI app like a client: POST /v1/chat/completions twice and
asserts the second response is an L1 cache hit.

Usage:
  python scripts/smoke_redis_l1.py
  REDIS_URL=redis://127.0.0.1:6379/15 python scripts/smoke_redis_l1.py
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


async def main() -> int:
    from httpx import ASGITransport, AsyncClient

    from daari.cache.redis_semantic import RedisSemanticCache
    from daari.config.settings import Settings
    from daari.gateway.internal import DaariMeta, InternalRequest, InternalResponse
    from daari.router.router import AppContext
    from daari.server.app import create_app

    redis_url = os.environ.get("REDIS_URL", "").strip()
    settings = Settings()
    settings.cache.backend = "redis"
    settings.cache.l0.enabled = False
    settings.cache.l1.enabled = True
    settings.cache.l1.similarity_threshold = 0.5
    if redis_url:
        settings.cache.redis_url = redis_url
        settings.cache.redis_l1_prefix = "daari:smoke:l1:"

    class FakeRedis:
        def __init__(self) -> None:
            self.data: dict[str, str] = {}

        def get(self, key: str):
            return self.data.get(key)

        def set(self, key: str, value: str, ex: int | None = None):
            self.data[key] = value

    class FixedEmbedder:
        async def embed(self, text: str):
            return [1.0, 0.0, 0.0] if text.strip() else None

    app = create_app(settings)
    ctx = AppContext.from_settings(settings)
    client = None
    if not redis_url:
        client = FakeRedis()
    ctx.semantic_cache = RedisSemanticCache(
        settings.cache.redis_url,
        FixedEmbedder(),
        client=client,
        enabled=True,
        similarity_threshold=0.5,
        normalize_inputs=False,
        prefix=settings.cache.redis_l1_prefix,
    )
    ctx.router.semantic_cache = ctx.semantic_cache
    app.state.ctx = ctx

    async def fake_execute(request: InternalRequest) -> InternalResponse:
        return InternalResponse(
            content="smoke-l1-body",
            model="llama3.2:3b",
            daari_meta=DaariMeta(
                tier="L3", executor="ollama", provider_id="ollama", latency_ms=1
            ),
        )

    for executor in (ctx.router.ollama, ctx.router.ollama_l3, ctx.router.ollama_l4, ctx.router.ollama_l5):
        executor.execute = fake_execute  # type: ignore[method-assign]

    payload = {
        "model": "daari",
        "messages": [{"role": "user", "content": "smoke redis l1 prompt"}],
    }
    headers = {"X-Daari-Meta": "true"}
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://smoke") as http:
        health = await http.get("/health")
        first = await http.post("/v1/chat/completions", json=payload, headers=headers)
        second = await http.post(
            "/v1/chat/completions",
            json={
                "model": "daari",
                "messages": [{"role": "user", "content": "smoke redis l1 paraphrase"}],
            },
            headers=headers,
        )

    first_body = first.json()
    second_body = second.json()
    print(f"health={health.status_code}")
    print(f"first_tier={first_body.get('daari_meta', {}).get('tier')}")
    print(f"second_tier={second_body.get('daari_meta', {}).get('tier')}")
    print(f"second_cache_hit={second_body.get('daari_meta', {}).get('cache_hit')}")
    print(f"mode={'real-redis' if redis_url else 'fake-redis'}")

    ok = (
        health.status_code == 200
        and first.status_code == 200
        and second.status_code == 200
        and second_body.get("daari_meta", {}).get("tier") == "L1"
        and second_body.get("daari_meta", {}).get("cache_hit") is True
        and "smoke-l1-body" in second_body["choices"][0]["message"]["content"]
    )
    print("PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
