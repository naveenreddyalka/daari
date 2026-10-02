"""Local-first MCP OAuth token mint beyond RFC 9728 discovery (#1293)."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from daari.gateway.mcp_oauth import (
    mcp_oauth_local_as_enabled,
    protected_resource_metadata,
)
from daari.router.router import AppContext
from daari.server.app import create_app


def _app(settings):
    application = create_app(settings)
    application.state.ctx = AppContext.from_settings(settings)
    return application


def test_local_as_defaults_off(settings):
    assert mcp_oauth_local_as_enabled(settings) is False
    assert settings.integrations.mcp_oauth.local_as is False


def test_discovery_lists_local_as_when_enabled(settings):
    settings.integrations.mcp_oauth.protected_resource = True
    settings.integrations.mcp_oauth.local_as = True
    settings.integrations.mcp_oauth.resource = "http://gateway.example"
    settings.integrations.mcp_oauth.authorization_servers = []
    doc = protected_resource_metadata(settings)
    assert doc["authorization_servers"] == ["http://gateway.example"]


@pytest.mark.asyncio
async def test_as_metadata_and_token_mint_then_tools_list(settings):
    settings.server.api_key = "secret-key"
    settings.integrations.mcp_oauth.protected_resource = True
    settings.integrations.mcp_oauth.local_as = True
    settings.integrations.mcp_oauth.resource = "http://test"
    settings.integrations.mcp_oauth.token_ttl_seconds = 600
    app = _app(settings)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        meta = await client.get("/.well-known/oauth-protected-resource")
        assert meta.status_code == 200
        assert "http://test" in meta.json()["authorization_servers"]

        as_doc = await client.get("/.well-known/oauth-authorization-server")
        assert as_doc.status_code == 200
        body = as_doc.json()
        assert body["issuer"] == "http://test"
        assert body["token_endpoint"].endswith("/oauth/token")
        assert "client_credentials" in body["grant_types_supported"]

        token_resp = await client.post(
            "/oauth/token",
            data={
                "grant_type": "client_credentials",
                "client_id": "mcp-client",
                "client_secret": "secret-key",
                "scope": "mcp",
            },
        )
        assert token_resp.status_code == 200
        token_body = token_resp.json()
        assert token_body["token_type"] == "Bearer"
        assert token_body["expires_in"] == 600
        assert "access_token" in token_body
        access = token_body["access_token"]
        assert "secret-key" not in access
        assert "secret-key" not in token_resp.text

        ok = await client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
            headers={"Authorization": f"Bearer {access}"},
        )
        assert ok.status_code == 200
        assert "result" in ok.json()
        assert "tools" in ok.json()["result"]

        bad = await client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
            headers={"Authorization": "Bearer not-a-valid-token"},
        )
        assert bad.status_code == 401
        assert "WWW-Authenticate" in bad.headers


@pytest.mark.asyncio
async def test_expired_or_tampered_token_rejected(settings):
    settings.server.api_key = "secret-key"
    settings.integrations.mcp_oauth.protected_resource = True
    settings.integrations.mcp_oauth.local_as = True
    settings.integrations.mcp_oauth.token_ttl_seconds = 1
    settings.integrations.mcp_oauth.signing_secret = "unit-test-signing-secret"
    app = _app(settings)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        token_resp = await client.post(
            "/oauth/token",
            data={
                "grant_type": "client_credentials",
                "client_secret": "secret-key",
            },
        )
        access = token_resp.json()["access_token"]
        # Tamper payload segment.
        parts = access.split(".")
        tampered = parts[0] + "." + parts[1][:-1] + ("A" if parts[1][-1] != "A" else "B") + "." + parts[2]
        bad = await client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
            headers={"Authorization": f"Bearer {tampered}"},
        )
        assert bad.status_code == 401


@pytest.mark.asyncio
async def test_token_endpoint_absent_when_local_as_off(settings):
    settings.server.api_key = "secret-key"
    settings.integrations.mcp_oauth.protected_resource = True
    settings.integrations.mcp_oauth.local_as = False
    app = _app(settings)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        as_doc = await client.get("/.well-known/oauth-authorization-server")
        assert as_doc.status_code == 404
        token_resp = await client.post(
            "/oauth/token",
            data={"grant_type": "client_credentials", "client_secret": "secret-key"},
        )
        assert token_resp.status_code == 404


@pytest.mark.asyncio
async def test_bad_client_secret_rejected(settings):
    settings.server.api_key = "secret-key"
    settings.integrations.mcp_oauth.local_as = True
    settings.integrations.mcp_oauth.protected_resource = True
    app = _app(settings)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        token_resp = await client.post(
            "/oauth/token",
            data={
                "grant_type": "client_credentials",
                "client_secret": "wrong",
            },
        )
        assert token_resp.status_code == 401
        assert "access_token" not in token_resp.json()
