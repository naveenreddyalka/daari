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


@pytest.mark.asyncio
async def test_chat_forwards_x_request_id_to_ollama(settings, monkeypatch):
    """Inbound (or generated) id reaches the Ollama hop (#977)."""
    import httpx

    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            200,
            json={"message": {"role": "assistant", "content": "ok"}, "done": True},
        )

    transport = httpx.MockTransport(handler)
    original = httpx.AsyncClient

    def patched(*args, **kwargs):
        kwargs["transport"] = transport
        return original(*args, **kwargs)

    monkeypatch.setattr("daari.router.router.httpx.AsyncClient", patched)
    settings.cache.l0.enabled = False
    settings.cache.l1.enabled = False
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    transport_asgi = ASGITransport(app=app)
    async with AsyncClient(transport=transport_asgi, base_url="http://test") as client:
        response = await client.post(
            "/v1/chat/completions",
            json={
                "model": "llama3.2:3b",
                "messages": [{"role": "user", "content": "hi"}],
            },
            headers={"X-Request-ID": "chat-corr-77", "X-Daari-No-Cache": "true"},
        )
    assert response.status_code == 200, response.text
    assert response.headers["x-request-id"] == "chat-corr-77"
    chat_calls = [r for r in seen if r.method == "POST" and r.url.path.endswith("/api/chat")]
    assert chat_calls, f"expected an Ollama chat call, saw {[str(r.url) for r in seen]}"
    assert chat_calls[0].headers.get("x-request-id") == "chat-corr-77"


@pytest.mark.asyncio
async def test_asr_forwards_x_request_id_upstream(settings, monkeypatch):
    """ASR modality posts carry the same correlation id (#977)."""
    import httpx

    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"text": "hello"})

    original = httpx.AsyncClient

    class Patched(original):
        def __init__(self, *args, **kwargs):
            if kwargs.get("transport") is None:
                kwargs["transport"] = httpx.MockTransport(handler)
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", Patched)
    monkeypatch.setattr("daari.gateway.transcriptions.httpx.AsyncClient", Patched)
    settings.asr.base_url = "http://asr.local/v1"
    settings.asr.model = "whisper-1"
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/audio/transcriptions",
            data={"model": "whisper-1", "response_format": "json"},
            files={"file": ("a.wav", b"RIFF", "audio/wav")},
            headers={"X-Request-ID": "asr-corr-55"},
        )
    assert response.status_code == 200, response.text
    assert seen
    assert seen[0].headers.get("x-request-id") == "asr-corr-55"
