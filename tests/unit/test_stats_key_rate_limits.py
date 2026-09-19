"""GET /v1/daari/stats includes per-key rpd remaining (#749)."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from daari.auth.rate_limit import MemoryCounterBackend, RateLimiter
from daari.auth.virtual_keys import VirtualKeyStore
from daari.router.router import AppContext
from daari.server.app import create_app


def _app(settings, store, limiter):
    settings.server.api_key = "master"
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    app.state.virtual_key_store = store
    app.state.ctx.virtual_key_store = store
    app.state.rate_limiter = limiter
    return app


@pytest.mark.asyncio
async def test_stats_omits_keys_without_rpd(settings, tmp_path):
    settings.server.virtual_keys.path = str(tmp_path / "vk.sqlite3")
    store = VirtualKeyStore(settings.virtual_keys_path)
    store.create("idle", rpd=0)
    app = _app(settings, store, RateLimiter(MemoryCounterBackend()))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            "/v1/daari/stats",
            headers={"Authorization": "Bearer master"},
        )
    assert response.status_code == 200
    assert response.json()["key_rate_limits"] == []


@pytest.mark.asyncio
async def test_stats_includes_key_rpd_without_consuming_cap(settings, tmp_path):
    settings.server.virtual_keys.path = str(tmp_path / "vk.sqlite3")
    store = VirtualKeyStore(settings.virtual_keys_path)
    created = store.create("alice", rpd=5)
    limiter = RateLimiter(MemoryCounterBackend())
    assert limiter.check(key_id=created.key.key_id, model="m", tokens=1, rpd=5).allowed
    app = _app(settings, store, limiter)
    headers = {"Authorization": f"Bearer {created.plaintext}"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        first = await client.get("/v1/daari/stats", headers=headers)
        second = await client.get("/v1/daari/stats", headers=headers)
    assert first.status_code == 200
    row = first.json()["key_rate_limits"][0]
    assert row == {"key": "alice", "kind": "rpd", "limit": 5, "remaining": 4}
    assert created.plaintext not in first.text
    assert second.json()["key_rate_limits"][0]["remaining"] == 4
