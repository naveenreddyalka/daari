"""Optional observability.metrics_port scrape listener (#594)."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from daari.observability.metrics_listen import start_metrics_listener
from daari.router.router import AppContext
from daari.server.app import create_app


@pytest.mark.asyncio
async def test_metrics_port_scrape_open_while_api_port_requires_key(settings):
    settings.server.api_key = "sekret"
    settings.observability.prometheus = True
    settings.observability.metrics_port = 0  # start helper picks ephemeral

    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)

    bound, stop = await start_metrics_listener(app, host="127.0.0.1", port=0)
    try:
        async with AsyncClient() as http:
            open_scrape = await http.get(f"http://127.0.0.1:{bound}/metrics")
        assert open_scrape.status_code == 200
        assert "daari_requests_total" in open_scrape.text or "HELP" in open_scrape.text

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            denied = await client.get("/metrics")
            assert denied.status_code == 401
            allowed = await client.get(
                "/metrics", headers={"Authorization": "Bearer sekret"}
            )
            assert allowed.status_code == 200
            assert allowed.text == open_scrape.text
    finally:
        await stop()


@pytest.mark.asyncio
async def test_metrics_port_noop_when_prometheus_disabled(settings):
    settings.server.api_key = "sekret"
    settings.observability.prometheus = False
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)

    bound, stop = await start_metrics_listener(app, host="127.0.0.1", port=0)
    try:
        async with AsyncClient() as http:
            response = await http.get(f"http://127.0.0.1:{bound}/metrics")
        assert response.status_code == 404
    finally:
        await stop()
