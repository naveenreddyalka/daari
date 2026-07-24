"""F3: web UI config editor endpoints (issue #115)."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from daari.router.router import AppContext
from daari.server.app import create_app


@pytest.mark.asyncio
async def test_config_editor_disabled_404(settings):
    settings.observability.config_editor = False
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        assert (await client.get("/v1/daari/config")).status_code == 404


@pytest.mark.asyncio
async def test_config_editor_get_and_patch(settings):
    settings.observability.config_editor = True
    settings.routing.confidence_threshold = 0.7
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        got = await client.get("/v1/daari/config")
        assert got.status_code == 200
        body = got.json()
        assert body["routing"]["confidence_threshold"] == 0.7
        patched = await client.patch(
            "/v1/daari/config",
            json={"routing": {"confidence_threshold": 0.55, "prefer": "latency"}},
        )
        assert patched.status_code == 200
        assert patched.json()["routing"]["confidence_threshold"] == 0.55
        assert patched.json()["routing"]["prefer"] == "latency"
        assert app.state.ctx.router.confidence_threshold == 0.55
        assert app.state.ctx.router.model_preference == "latency"


@pytest.mark.asyncio
async def test_config_editor_requires_auth(settings):
    settings.server.api_key = "sekret"
    settings.observability.config_editor = True
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        denied = await client.get("/v1/daari/config")
        assert denied.status_code == 401
        ok = await client.get(
            "/v1/daari/config", headers={"Authorization": "Bearer sekret"}
        )
        assert ok.status_code == 200
