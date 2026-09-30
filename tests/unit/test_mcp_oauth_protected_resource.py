"""RFC 9728 OAuth protected-resource discovery for /mcp (#1262)."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from daari.gateway.mcp_oauth import (
    mcp_oauth_enabled,
    protected_resource_metadata,
    www_authenticate_header,
)
from daari.router.router import AppContext
from daari.server.app import create_app
from daari.setup.doctor import _check_mcp_oauth_protected_resource


def test_flag_defaults_off(settings):
    assert mcp_oauth_enabled(settings) is False
    assert settings.integrations.mcp_oauth.protected_resource is False


def test_metadata_json_shape(settings):
    settings.integrations.mcp_oauth.protected_resource = True
    settings.integrations.mcp_oauth.resource = "http://gateway.example"
    settings.integrations.mcp_oauth.authorization_servers = ["https://idp.example"]
    settings.integrations.mcp_oauth.scopes_supported = ["mcp", "openid"]
    doc = protected_resource_metadata(settings)
    assert doc["resource"] == "http://gateway.example/mcp"
    assert doc["authorization_servers"] == ["https://idp.example"]
    assert doc["scopes_supported"] == ["mcp", "openid"]


def test_www_authenticate_references_metadata(settings):
    settings.integrations.mcp_oauth.resource = "http://gateway.example"
    header = www_authenticate_header(settings)
    assert "Bearer" in header
    assert "resource_metadata=" in header
    assert "/.well-known/oauth-protected-resource" in header


def test_doctor_tips_when_auth_on_without_metadata(settings):
    settings.server.api_key = "secret"
    settings.integrations.mcp_oauth.protected_resource = False
    row = _check_mcp_oauth_protected_resource(settings)
    assert row.ok is False
    assert "protected_resource" in row.detail


def test_doctor_ok_when_metadata_enabled(settings):
    settings.server.api_key = "secret"
    settings.integrations.mcp_oauth.protected_resource = True
    row = _check_mcp_oauth_protected_resource(settings)
    assert row.ok is True


@pytest.mark.asyncio
async def test_well_known_served_when_enabled(settings):
    settings.integrations.mcp_oauth.protected_resource = True
    settings.integrations.mcp_oauth.authorization_servers = ["https://idp.example"]
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/.well-known/oauth-protected-resource")
        scoped = await client.get("/.well-known/oauth-protected-resource/mcp")
    assert response.status_code == 200
    body = response.json()
    assert body["resource"].endswith("/mcp")
    assert body["authorization_servers"] == ["https://idp.example"]
    assert "scopes_supported" in body
    assert scoped.status_code == 200
    assert scoped.json()["resource"].endswith("/mcp")


@pytest.mark.asyncio
async def test_unauthenticated_mcp_challenge_when_enabled(settings):
    settings.server.api_key = "secret"
    settings.integrations.mcp_oauth.protected_resource = True
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "ping"})
    assert response.status_code == 401
    assert "WWW-Authenticate" in response.headers
    assert "resource_metadata=" in response.headers["WWW-Authenticate"]
    assert "/.well-known/oauth-protected-resource" in response.headers["WWW-Authenticate"]


@pytest.mark.asyncio
async def test_unauthenticated_mcp_unchanged_when_disabled(settings):
    settings.server.api_key = "secret"
    settings.integrations.mcp_oauth.protected_resource = False
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "ping"})
    assert response.status_code == 401
    assert "WWW-Authenticate" not in response.headers
