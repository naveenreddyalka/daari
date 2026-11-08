"""GET /v1/daari/stats exposes virtual_model_latency_slo_ms (#2135)."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from daari.router.router import AppContext
from daari.server.app import create_app


def _app(settings):
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    return app


@pytest.mark.asyncio
async def test_stats_includes_virtual_model_latency_slo_ms_when_set(settings):
    settings.routing.virtual_models = {"chat": ["L3", "L4"]}
    settings.routing.virtual_model_latency_slo_ms = {"chat": 500.0}
    app = _app(settings)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/v1/daari/stats")

    assert response.status_code == 200
    body = response.json()
    assert body["virtual_model_latency_slo_ms"] == {"chat": 500.0}


@pytest.mark.asyncio
async def test_stats_virtual_model_latency_slo_ms_empty_when_unset(settings):
    settings.routing.virtual_models = {"chat": ["L3"]}
    settings.routing.virtual_model_latency_slo_ms = {}
    app = _app(settings)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/v1/daari/stats")

    assert response.status_code == 200
    body = response.json()
    assert body["virtual_model_latency_slo_ms"] == {}
