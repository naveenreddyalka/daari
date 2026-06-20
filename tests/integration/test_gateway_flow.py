"""Gateway + router + cache integration (mocked Ollama)."""

from __future__ import annotations

import json

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


@pytest.mark.asyncio
async def test_anthropic_messages_adapter_routes_to_daari(app, monkeypatch):
    async def fake_execute(request: InternalRequest) -> InternalResponse:
        return InternalResponse(
            content="anthropic-compatible-response",
            model="claude-sonnet-4-20250514",
            daari_meta=DaariMeta(
                tier="L3",
                executor="ollama",
                provider_id="ollama:l3",
                latency_ms=7,
            ),
        )

    monkeypatch.setattr(app.state.ctx.router.ollama, "execute", fake_execute)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/v1/messages",
            json={
                "model": "claude-sonnet-4-20250514",
                "messages": [{"role": "user", "content": "Explain this file."}],
                "max_tokens": 256,
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["type"] == "message"
    assert payload["content"][0]["text"] == "anthropic-compatible-response"
    assert payload["daari_meta"]["tier"] == "L3"


@pytest.mark.asyncio
async def test_stream_chunks_include_daari_meta(app, monkeypatch):
    async def fake_stream(_request: InternalRequest):
        yield {"message": {"content": "Hello"}}
        yield {"done": True}

    monkeypatch.setattr(app.state.ctx.router.ollama, "stream", fake_stream)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/v1/chat/completions",
            json={
                "model": "llama3.2:3b",
                "messages": [{"role": "user", "content": "stream this"}],
                "stream": True,
            },
        )

    assert response.status_code == 200
    lines = [line for line in response.text.splitlines() if line.startswith("data: ") and line != "data: [DONE]"]
    first_payload = json.loads(lines[0].replace("data: ", ""))
    assert first_payload["daari_meta"]["tier"] in {"L3", "L4", "L5"}
    assert first_payload["daari_meta"]["stream"] is True


@pytest.mark.asyncio
async def test_mcp_gateway_stub_is_explicit(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/v1/mcp/query", json={})
    assert response.status_code == 501
