"""X-Request-ID sanitize, echo, and spend correlation (#965)."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from daari.gateway.internal import DaariMeta, InternalRequest, InternalResponse
from daari.gateway.request_id import resolve_request_id, sanitize_request_id
from daari.router.router import AppContext
from daari.server.app import create_app


def test_sanitize_rejects_empty_control_and_overlong():
    assert sanitize_request_id(None) is None
    assert sanitize_request_id("") is None
    assert sanitize_request_id("  ") is None
    assert sanitize_request_id("has space") is None
    assert sanitize_request_id("bad\nid") is None
    assert sanitize_request_id("a" * 129) is None
    assert sanitize_request_id("req-abc_123.OK") == "req-abc_123.OK"


def test_resolve_prefers_header_else_generates():
    assert resolve_request_id({"x-request-id": "client-42"}) == "client-42"
    assert resolve_request_id({"X-Request-Id": "Alt-Case"}) == "Alt-Case"
    generated = resolve_request_id({})
    assert len(generated) == 16
    assert generated.isalnum()


@pytest.mark.asyncio
async def test_chat_completions_echoes_x_request_id(settings, monkeypatch):
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)

    async def fake_route(request: InternalRequest) -> InternalResponse:
        assert request.meta.request_id == "proxy-corr-9"
        return InternalResponse(
            content="ok",
            model="llama3.2:3b",
            daari_meta=DaariMeta(tier="L3", executor="ollama", provider_id="ollama"),
        )

    monkeypatch.setattr(app.state.ctx.router, "route", fake_route)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/v1/chat/completions",
            json={
                "model": "llama3.2:3b",
                "messages": [{"role": "user", "content": "hi"}],
            },
            headers={"X-Request-ID": "proxy-corr-9"},
        )
    assert response.status_code == 200
    assert response.headers["x-request-id"] == "proxy-corr-9"


@pytest.mark.asyncio
async def test_chat_completions_generates_x_request_id_when_absent(settings, monkeypatch):
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    seen: list[str] = []

    async def fake_route(request: InternalRequest) -> InternalResponse:
        seen.append(request.meta.request_id or "")
        return InternalResponse(
            content="ok",
            model="llama3.2:3b",
            daari_meta=DaariMeta(tier="L3", executor="ollama", provider_id="ollama"),
        )

    monkeypatch.setattr(app.state.ctx.router, "route", fake_route)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/v1/chat/completions",
            json={
                "model": "llama3.2:3b",
                "messages": [{"role": "user", "content": "hi"}],
            },
        )
    assert response.status_code == 200
    echoed = response.headers["x-request-id"]
    assert echoed == seen[0]
    assert len(echoed) == 16
