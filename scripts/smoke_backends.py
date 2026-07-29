#!/usr/bin/env python3
"""Smoke: Redis L0/L1 + Postgres ledger (issue #142).

Default (no Docker): FakeRedis + in-memory Postgres stand-in — CI-safe.
Live: REDIS_URL + POSTGRES_URL (see scripts/smoke_backends.sh).

Usage:
  python scripts/smoke_backends.py
  REDIS_URL=redis://127.0.0.1:6379/15 \\
    POSTGRES_URL=postgresql://daari:daari@127.0.0.1:5432/daari \\
    python scripts/smoke_backends.py
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


class FakeRedis:
    def __init__(self) -> None:
        self.data: dict[str, str] = {}

    def get(self, key: str):
        return self.data.get(key)

    def set(self, key: str, value: str, ex: int | None = None):
        self.data[key] = value

    def delete(self, key: str):
        self.data.pop(key, None)


class _MemCursor:
    def __init__(self, store: dict) -> None:
        self._store = store
        self._rows: list = []

    def execute(self, sql: str, params=None) -> None:
        sql_l = " ".join(sql.lower().split())
        params = tuple(params or ())
        if "create table" in sql_l:
            return
        if "insert into usage" in sql_l:
            day, tier, hits, pc, cc = params[0], params[1], params[2], params[3], params[4]
            key = (day, tier)
            usage = self._store.setdefault("usage", {})
            prev = usage.get(key, (0, 0, 0, 0))
            usage[key] = (
                prev[0] + 1,
                prev[1] + int(hits),
                prev[2] + int(pc),
                prev[3] + int(cc),
            )
            return
        if "insert into client_usage" in sql_l:
            return
        if "from usage where day" in sql_l and "select day, tier" in sql_l:
            cutoff = params[0]
            self._rows = [
                (day, tier, req, hits, pc, cc)
                for (day, tier), (req, hits, pc, cc) in self._store.get("usage", {}).items()
                if day >= cutoff
            ]
            return
        if "from usage where day" in sql_l and "sum" in sql_l:
            self._rows = [(0,)]
            return
        self._rows = []

    def fetchall(self):
        return list(self._rows)

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class _MemConn:
    def __init__(self, store: dict) -> None:
        self._store = store

    def cursor(self):
        return _MemCursor(self._store)

    def commit(self):
        return None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


async def main() -> int:
    from httpx import ASGITransport, AsyncClient

    from daari.cache.redis_exact import RedisExactCache
    from daari.cache.redis_semantic import RedisSemanticCache
    from daari.config.settings import Settings
    from daari.gateway.internal import DaariMeta, InternalRequest, InternalResponse
    from daari.observability.postgres_usage import PostgresUsageLedger
    from daari.router.router import AppContext
    from daari.server.app import create_app

    redis_url = os.environ.get("REDIS_URL", "").strip()
    postgres_url = os.environ.get("POSTGRES_URL", "").strip()
    live = bool(redis_url and postgres_url)
    mode = "live" if live else "offline-fakes"

    settings = Settings()
    settings.cache.backend = "redis"
    settings.cache.l0.enabled = True
    settings.cache.l1.enabled = True
    settings.cache.l1.similarity_threshold = 0.5
    settings.observability.backend = "postgres"
    settings.observability.postgres_url = postgres_url or "postgresql://fake/daari"
    if redis_url:
        settings.cache.redis_url = redis_url
        settings.cache.redis_l1_prefix = "daari:smoke142:l1:"

    class FixedEmbedder:
        async def embed(self, text: str):
            return [1.0, 0.0, 0.0] if text.strip() else None

    shared = None if redis_url else FakeRedis()
    app = create_app(settings)
    ctx = AppContext.from_settings(settings)

    ctx.cache = RedisExactCache(
        settings.cache.redis_url,
        client=shared,
        enabled=True,
        prefix="daari:smoke142:l0:",
    )
    ctx.semantic_cache = RedisSemanticCache(
        settings.cache.redis_url,
        FixedEmbedder(),
        client=shared,
        enabled=True,
        similarity_threshold=0.5,
        normalize_inputs=False,
        prefix=settings.cache.redis_l1_prefix,
    )
    ctx.router.cache = ctx.cache
    ctx.router.semantic_cache = ctx.semantic_cache

    mem_store: dict = {}
    if not postgres_url:
        ledger = PostgresUsageLedger(settings.observability.postgres_url, enabled=False)
        ledger.enabled = True
        ledger._connect = lambda: _MemConn(mem_store)  # type: ignore[method-assign]
        ctx.router.usage_ledger = ledger
    else:
        if not isinstance(ctx.router.usage_ledger, PostgresUsageLedger):
            print("FAIL: expected PostgresUsageLedger")
            return 1
        if not ctx.router.usage_ledger.enabled:
            print("FAIL: PostgresUsageLedger disabled (connect failed)")
            return 1

    async def fake_execute(request: InternalRequest) -> InternalResponse:
        return InternalResponse(
            content="smoke-backends-body",
            model="llama3.2:3b",
            daari_meta=DaariMeta(
                tier="L3", executor="ollama", provider_id="ollama", latency_ms=1
            ),
        )

    for executor in (ctx.router.ollama, ctx.router.ollama_l3, ctx.router.ollama_l4, ctx.router.ollama_l5):
        executor.execute = fake_execute  # type: ignore[method-assign]

    app.state.ctx = ctx
    headers = {"X-Daari-Meta": "true"}
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://smoke") as http:
        health = await http.get("/health")
        # L0: identical prompt twice
        exact = {
            "model": "daari",
            "messages": [{"role": "user", "content": "smoke backends exact prompt"}],
        }
        first = await http.post("/v1/chat/completions", json=exact, headers=headers)
        second = await http.post("/v1/chat/completions", json=exact, headers=headers)
        # L1: paraphrase (same FixedEmbedder vector); L0 misses so L1 hits
        para = {
            "model": "daari",
            "messages": [{"role": "user", "content": "smoke backends paraphrase"}],
        }
        third = await http.post("/v1/chat/completions", json=para, headers=headers)

    ledger = ctx.router.usage_ledger
    ledger.record(tier="L3", prompt_chars=10, completion_chars=5)
    report = ledger.report(days=1)

    first_meta = first.json().get("daari_meta", {})
    second_meta = second.json().get("daari_meta", {})
    third_meta = third.json().get("daari_meta", {})

    print(f"mode={mode}")
    print(f"health={health.status_code}")
    print(f"L0_miss_tier={first_meta.get('tier')} hit={first_meta.get('cache_hit')}")
    print(f"L0_hit_tier={second_meta.get('tier')} hit={second_meta.get('cache_hit')}")
    print(f"L1_hit_tier={third_meta.get('tier')} hit={third_meta.get('cache_hit')}")
    print(f"ledger_enabled={report.get('enabled')} totals={report.get('totals')}")

    ok = (
        health.status_code == 200
        and first.status_code == 200
        and second.status_code == 200
        and third.status_code == 200
        and second_meta.get("tier") == "L0"
        and second_meta.get("cache_hit") is True
        and third_meta.get("tier") == "L1"
        and third_meta.get("cache_hit") is True
        and report.get("enabled") is True
        and (report.get("totals") or {}).get("requests", 0) >= 1
    )
    print("PASS smoke_backends" if ok else "FAIL smoke_backends")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
