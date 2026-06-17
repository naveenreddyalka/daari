"""Gateway + router + cache integration (mocked Ollama)."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from daari.gateway.internal import DaariMeta, InternalRequest, InternalResponse
from daari.router.router import AppContext
from daari.server.app import create_app


@pytest.fixture
def app(settings):
    application = create_app(settings)
    application.state.ctx = AppContext.from_settings(settings)
    return application


@pytest.mark.asyncio
async def test_full_stack_l0_after_l3(app, monkeypatch):
    async def fake_execute(request: InternalRequest) -> InternalResponse:
        return InternalResponse(
            content="from-ollama",
            model="llama3.2:3b",
            daari_meta=DaariMeta(
                tier="L3",
                executor="ollama",
                provider_id="ollama",
                latency_ms=50,
            ),
        )

    monkeypatch.setattr(app.state.ctx.router.ollama, "execute", fake_execute)
    payload = {
        "model": "llama3.2:3b",
        "messages": [{"role": "user", "content": "integration smoke"}],
    }

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        first = await client.post("/v1/chat/completions", json=payload)
        second = await client.post("/v1/chat/completions", json=payload)
        stats = await client.get("/v1/daari/stats")

    assert first.status_code == 200
    assert first.json()["daari_meta"]["tier"] == "L3"
    assert second.json()["daari_meta"]["tier"] == "L0"
    assert stats.json()["total_requests"] == 2


@pytest.mark.asyncio
async def test_no_cache_header_skips_l0(app, monkeypatch):
    call_count = 0

    async def fake_execute(request: InternalRequest) -> InternalResponse:
        nonlocal call_count
        call_count += 1
        return InternalResponse(
            content=f"hit-{call_count}",
            model="llama3.2:3b",
            daari_meta=DaariMeta(
                tier="L3",
                executor="ollama",
                provider_id="ollama",
                latency_ms=1,
            ),
        )

    monkeypatch.setattr(app.state.ctx.router.ollama, "execute", fake_execute)
    payload = {
        "model": "llama3.2:3b",
        "messages": [{"role": "user", "content": "no cache please"}],
    }
    headers = {"X-Daari-No-Cache": "true"}

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        first = await client.post("/v1/chat/completions", json=payload, headers=headers)
        second = await client.post("/v1/chat/completions", json=payload, headers=headers)

    assert first.json()["daari_meta"]["tier"] == "L3"
    assert second.json()["daari_meta"]["tier"] == "L3"
    assert call_count == 2
