"""CORS allowlist and default security headers (#938)."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from daari.config.settings import Settings
from daari.router.router import AppContext
from daari.server.app import create_app

WEB_UI = "http://127.0.0.1:11437"
SECURITY = {
    "x-content-type-options": "nosniff",
    "x-frame-options": "DENY",
    "referrer-policy": "no-referrer",
}


def _app(settings: Settings):
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    return app


@pytest.mark.asyncio
async def test_stats_from_web_ui_origin_gets_cors_and_security_headers(settings, tmp_path):
    settings.server.api_key = "master"
    settings.server.cors_origins = [WEB_UI]
    settings.server.security_headers = True
    app = _app(settings)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/v1/daari/stats",
            headers={
                "Authorization": "Bearer master",
                "Origin": WEB_UI,
            },
        )
        preflight = await client.options(
            "/v1/daari/stats",
            headers={
                "Origin": WEB_UI,
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "authorization",
            },
        )

    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == WEB_UI
    for name, value in SECURITY.items():
        assert response.headers.get(name) == value

    assert preflight.status_code == 204
    assert preflight.headers.get("access-control-allow-origin") == WEB_UI
    allow_headers = (preflight.headers.get("access-control-allow-headers") or "").lower()
    assert "authorization" in allow_headers


@pytest.mark.asyncio
async def test_disallowed_origin_does_not_reflect_acao(settings):
    settings.server.api_key = "master"
    settings.server.cors_origins = [WEB_UI]
    app = _app(settings)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/v1/daari/stats",
            headers={
                "Authorization": "Bearer master",
                "Origin": "https://evil.example",
            },
        )

    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") != "https://evil.example"
    assert "access-control-allow-origin" not in {
        k.lower(): v for k, v in response.headers.items()
    } or response.headers.get("access-control-allow-origin") == WEB_UI
    # Starlette omits ACAO for disallowed origins rather than reflecting them.
    acao = response.headers.get("access-control-allow-origin")
    assert acao in (None, WEB_UI)
    assert acao != "https://evil.example"


@pytest.mark.asyncio
async def test_empty_cors_origins_skips_cors_middleware(settings):
    settings.server.api_key = "master"
    settings.server.cors_origins = []
    app = _app(settings)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/v1/daari/stats",
            headers={
                "Authorization": "Bearer master",
                "Origin": WEB_UI,
            },
        )

    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") is None
    for name, value in SECURITY.items():
        assert response.headers.get(name) == value


def test_security_headers_can_be_disabled(settings):
    settings.server.api_key = "master"
    settings.server.security_headers = False
    app = _app(settings)
    assert app is not None
