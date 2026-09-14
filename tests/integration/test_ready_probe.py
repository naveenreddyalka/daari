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


@pytest.mark.asyncio
async def test_ready_redis_degraded_when_redis_down(settings, tmp_path, monkeypatch):
    """cache.backend=redis + Redis down → degraded-but-200 (#463)."""
    from daari.auth.rate_limit import build_rate_limiter

    settings.cache.backend = "redis"
    settings.rate_limit.rpm = 10
    settings.server.virtual_keys.path = str(tmp_path / "vk.sqlite3")

    class Boom:
        def ping(self):
            raise ConnectionError("redis down")

        def pipeline(self):
            raise ConnectionError("redis down")

    async def backend_ok(probe_url: str, timeout: float = 2.0) -> str:
        return "ok"

    monkeypatch.setattr("daari.gateway.openai.check_model_backend", backend_ok)
    monkeypatch.setattr(
        "daari.gateway.request_log.log_gateway_event",
        lambda *args, **kwargs: None,
    )
    app = _app(settings)
    app.state.rate_limiter = build_rate_limiter(settings, redis_client=Boom())
    # Force degraded path so /ready sees fallback-active semantics.
    app.state.rate_limiter.check(key_id="probe", model="daari", tokens=1, rpm=10)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/ready")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "degraded"
    assert body["checks"]["redis"] == "ConnectionError"
    assert body["checks"]["cache"] == "ok"
    assert body["checks"]["model_backend"] == "ok"


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
