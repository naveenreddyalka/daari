"""GET /v1/daari/stats includes team rpd remaining (#741)."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from daari.auth.rate_limit import MemoryCounterBackend, RateLimiter
from daari.auth.virtual_keys import VirtualKeyStore
from daari.router.router import AppContext
from daari.server.app import create_app


@pytest.mark.asyncio
async def test_stats_team_rate_limits_empty_without_ceilings(settings, tmp_path):
    settings.server.virtual_keys.path = str(tmp_path / "vk.sqlite3")
    store = VirtualKeyStore(settings.virtual_keys_path)
    store.create_team("ops", rpd=0, rpm=0, tpm=0)
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    app.state.virtual_key_store = store
    app.state.ctx.virtual_key_store = store
    app.state.rate_limiter = RateLimiter(MemoryCounterBackend())

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/v1/daari/stats")

    assert response.status_code == 200
    assert response.json()["team_rate_limits"] == []


@pytest.mark.asyncio
async def test_stats_includes_team_rpd_remaining(settings, tmp_path):
    settings.server.virtual_keys.path = str(tmp_path / "vk.sqlite3")
    store = VirtualKeyStore(settings.virtual_keys_path)
    team = store.create_team("eng", rpd=3)
    limiter = RateLimiter(MemoryCounterBackend())
    assert limiter.check(
        key_id="alice",
        model="daari",
        tokens=1,
        team_id=team.team_id,
        team_rpd=3,
    ).allowed
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    app.state.virtual_key_store = store
    app.state.ctx.virtual_key_store = store
    app.state.rate_limiter = limiter

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/v1/daari/stats")

    assert response.status_code == 200
    rows = response.json()["team_rate_limits"]
    rpd = next(row for row in rows if row["kind"] == "rpd")
    assert rpd == {"team": "eng", "kind": "rpd", "limit": 3, "remaining": 2}
