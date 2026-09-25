"""Request body size cap (#933)."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from daari.config.settings import Settings
from daari.gateway.internal import DaariMeta, InternalRequest, InternalResponse
from daari.observability.metrics import Metrics
from daari.router.router import AppContext
from daari.server.app import create_app
from daari.server.body_limit import (
    DEFAULT_MAX_BODY_BYTES,
    UPLOAD_ROUTE_FLOOR_BYTES,
    body_limit_for_path,
    body_too_large_response,
)
from tests.conftest import META_HEADERS


def test_default_max_body_bytes() -> None:
    assert Settings().server.max_body_bytes == DEFAULT_MAX_BODY_BYTES


def test_body_limit_upload_routes_raise_floor() -> None:
    assert body_limit_for_path(
        "/v1/chat/completions", max_body_bytes=1024, files_max_total=0
    ) == 1024
    assert (
        body_limit_for_path("/v1/files", max_body_bytes=1024, files_max_total=0)
        == UPLOAD_ROUTE_FLOOR_BYTES
    )
    assert (
        body_limit_for_path(
            "/v1/files", max_body_bytes=1024, files_max_total=200 * 1024 * 1024
        )
        == 200 * 1024 * 1024
    )
    assert (
        body_limit_for_path(
            "/v1/audio/transcriptions", max_body_bytes=1024, files_max_total=0
        )
        == UPLOAD_ROUTE_FLOOR_BYTES
    )
    assert (
        body_limit_for_path("/v1/images/edits", max_body_bytes=1024, files_max_total=0)
        == UPLOAD_ROUTE_FLOOR_BYTES
    )


def test_openai_and_anthropic_error_shapes() -> None:
    openai = body_too_large_response(path="/v1/chat/completions", limit=10, content_length=99)
    assert openai.status_code == 413
    payload = openai.body
    import json

    data = json.loads(payload)
    assert data["error"]["code"] == "request_too_large"
    assert data["error"]["type"] == "invalid_request_error"

    anthropic = body_too_large_response(path="/v1/messages", limit=10, content_length=99)
    data = json.loads(anthropic.body)
    assert data["type"] == "error"
    assert data["error"]["type"] == "invalid_request_error"


@pytest.mark.asyncio
async def test_oversized_content_length_returns_413(settings, monkeypatch):
    settings.server.max_body_bytes = 64
    application = create_app(settings)
    application.state.ctx = AppContext.from_settings(settings)
    application.state.ctx.metrics = Metrics()

    called = {"n": 0}

    async def fake_execute(request: InternalRequest) -> InternalResponse:
        called["n"] += 1
        return InternalResponse(
            content="ok",
            model="llama3.2:3b",
            daari_meta=DaariMeta(tier="L3", executor="ollama", provider_id="ollama"),
        )

    monkeypatch.setattr(application.state.ctx.router.ollama, "execute", fake_execute)

    transport = ASGITransport(app=application)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        denied = await client.post(
            "/v1/chat/completions",
            content=b'{"model":"x","messages":[{"role":"user","content":"' + b"x" * 200 + b'"}]}',
            headers={**META_HEADERS, "content-type": "application/json"},
        )
        ok = await client.post(
            "/v1/chat/completions",
            json={"model": "x", "messages": [{"role": "user", "content": "hi"}]},
            headers=META_HEADERS,
        )

    assert denied.status_code == 413
    body = denied.json()
    assert body["error"]["code"] == "request_too_large"
    assert ok.status_code == 200
    assert called["n"] == 1
    assert application.state.ctx.metrics.snapshot(include_histograms=True)["rejects"].get(
        "body_too_large", 0
    ) >= 1


@pytest.mark.asyncio
async def test_anthropic_oversized_body_native_shape(settings):
    settings.server.max_body_bytes = 32
    application = create_app(settings)
    application.state.ctx = AppContext.from_settings(settings)

    transport = ASGITransport(app=application)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        denied = await client.post(
            "/v1/messages",
            content=b'{"model":"x","messages":[{"role":"user","content":"' + b"y" * 200 + b'"}],"max_tokens":1}',
            headers={
                "content-type": "application/json",
                "anthropic-version": "2023-06-01",
                "x-api-key": "test",
            },
        )

    assert denied.status_code == 413
    body = denied.json()
    assert body["type"] == "error"
    assert body["error"]["type"] == "invalid_request_error"
