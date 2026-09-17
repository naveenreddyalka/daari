"""GET /v1/daari/stats exposes soft_warnings and rejects (#593)."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from daari.gateway.internal import DaariMeta, InternalRequest, InternalResponse, Message
from daari.router.router import AppContext
from daari.server.app import create_app


@pytest.mark.asyncio
async def test_stats_includes_empty_cliff_maps(settings):
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/v1/daari/stats")
    assert response.status_code == 200
    body = response.json()
    assert body["soft_warnings"] == {}
    assert body["rejects"] == {}
    assert "total_requests" in body
    assert "tiers" in body


@pytest.mark.asyncio
async def test_stats_includes_soft_warnings_and_rejects(settings):
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    metrics = app.state.ctx.metrics
    metrics.record_soft_warning("rate_limit")
    metrics.record_soft_warning("request_quota")
    metrics.record_reject("budget")
    metrics.record_reject("rate_limit")
    metrics.record_reject("rate_limit")

    async def fake_execute(request: InternalRequest) -> InternalResponse:
        return InternalResponse(
            content="ok",
            model="llama3.2:3b",
            daari_meta=DaariMeta(tier="L3", executor="ollama", latency_ms=1),
        )

    app.state.ctx.router.ollama.execute = fake_execute  # type: ignore[method-assign]

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # One real request so tiers/total stay non-empty without affecting cliff maps.
        await client.post(
            "/v1/chat/completions",
            json={
                "model": "daari",
                "messages": [{"role": "user", "content": "hi"}],
            },
            headers={"X-Daari-No-Cache": "true"},
        )
        response = await client.get("/v1/daari/stats")

    assert response.status_code == 200
    body = response.json()
    assert body["soft_warnings"] == {"rate_limit": 1, "request_quota": 1}
    assert body["rejects"] == {"budget": 1, "rate_limit": 2}
    assert body["total_requests"] >= 1
