"""Readiness probe for orchestrators (issue #105)."""

from __future__ import annotations

import httpx
import pytest
from httpx import ASGITransport, AsyncClient

from daari.gateway.openai import check_model_backend
from daari.router.router import AppContext
from daari.server.app import create_app


def _app(settings):
    application = create_app(settings)
    application.state.ctx = AppContext.from_settings(settings)
    return application


@pytest.mark.asyncio
async def test_ready_ok_when_backend_answers(settings, monkeypatch):
    app = _app(settings)

    async def backend_ok(probe_url: str, timeout: float = 2.0) -> str:
        assert probe_url.endswith("/api/version")
        return "ok"

    monkeypatch.setattr("daari.gateway.openai.check_model_backend", backend_ok)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/ready")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert body["checks"] == {"cache": "ok", "model_backend": "ok"}


@pytest.mark.asyncio
async def test_ready_503_when_backend_down(settings, monkeypatch):
    app = _app(settings)

    async def backend_down(probe_url: str, timeout: float = 2.0) -> str:
        return "ConnectError"

    monkeypatch.setattr("daari.gateway.openai.check_model_backend", backend_down)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/ready")
    assert response.status_code == 503
    assert response.json()["checks"]["model_backend"] == "ConnectError"


@pytest.mark.asyncio
async def test_ready_open_without_api_key_auth(settings, monkeypatch):
    settings.server.api_key = "sekret-key"
    app = _app(settings)

    async def backend_ok(probe_url: str, timeout: float = 2.0) -> str:
        return "ok"

    monkeypatch.setattr("daari.gateway.openai.check_model_backend", backend_ok)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/ready")  # no key — probes can't send one
    assert response.status_code == 200


class TestCheckModelBackend:
    @pytest.mark.asyncio
    async def test_ok_response(self, monkeypatch):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"version": "0.5.0"})

        original = httpx.AsyncClient

        def patched(**kwargs):
            kwargs["transport"] = httpx.MockTransport(handler)
            return original(**kwargs)

        monkeypatch.setattr(httpx, "AsyncClient", patched)
        assert await check_model_backend("http://test/api/version") == "ok"

    @pytest.mark.asyncio
    async def test_5xx_reports_status(self, monkeypatch):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(502)

        original = httpx.AsyncClient

        def patched(**kwargs):
            kwargs["transport"] = httpx.MockTransport(handler)
            return original(**kwargs)

        monkeypatch.setattr(httpx, "AsyncClient", patched)
        assert await check_model_backend("http://test/api/version") == "http 502"

    @pytest.mark.asyncio
    async def test_connection_error_reports_type(self, monkeypatch):
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("boom")

        original = httpx.AsyncClient

        def patched(**kwargs):
            kwargs["transport"] = httpx.MockTransport(handler)
            return original(**kwargs)

        monkeypatch.setattr(httpx, "AsyncClient", patched)
        assert await check_model_backend("http://test/api/version") == "ConnectError"
