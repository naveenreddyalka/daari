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


@pytest.mark.asyncio
async def test_token_mint_writes_audit_row(settings):
    """Successful mint records mcp_oauth.token_minted without the raw token (#1468)."""
    from daari.enterprise.postgres_audit import audit_log_from_settings
    from daari.gateway.mcp_oauth import AUDIT_TOKEN_MINTED

    settings.server.api_key = "secret-key"
    settings.integrations.mcp_oauth.protected_resource = True
    settings.integrations.mcp_oauth.local_as = True
    settings.integrations.mcp_oauth.token_ttl_seconds = 600
    app = _app(settings)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        token_resp = await client.post(
            "/oauth/token",
            data={
                "grant_type": "client_credentials",
                "client_secret": "secret-key",
                "scope": "mcp",
            },
        )
        assert token_resp.status_code == 200
        access = token_resp.json()["access_token"]

    entries = audit_log_from_settings(settings).list(limit=50)
    minted = [e for e in entries if e.get("action") == AUDIT_TOKEN_MINTED]
    assert minted, f"expected {AUDIT_TOKEN_MINTED} in {entries!r}"
    detail = minted[-1].get("detail") or {}
    if isinstance(detail, str):
        import json

        detail = json.loads(detail)
    assert detail.get("kind") == "master"
    assert detail.get("expires_in") == 600
    assert detail.get("scope") == "mcp"
    assert detail.get("token_fp")
    blob = str(minted[-1])
    assert access not in blob
    assert "secret-key" not in blob


@pytest.mark.asyncio
async def test_token_deny_writes_audit_row(settings):
    """invalid_client and unsupported_grant_type both audit as denied (#1468)."""
    from daari.enterprise.postgres_audit import audit_log_from_settings
    from daari.gateway.mcp_oauth import AUDIT_TOKEN_DENIED

    settings.server.api_key = "secret-key"
    settings.integrations.mcp_oauth.protected_resource = True
    settings.integrations.mcp_oauth.local_as = True
    app = _app(settings)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        bad_secret = await client.post(
            "/oauth/token",
            data={"grant_type": "client_credentials", "client_secret": "wrong"},
        )
        assert bad_secret.status_code == 401
        bad_grant = await client.post(
            "/oauth/token",
            data={"grant_type": "authorization_code", "client_secret": "secret-key"},
        )
        assert bad_grant.status_code == 400

    entries = audit_log_from_settings(settings).list(limit=50)
    denied = [e for e in entries if e.get("action") == AUDIT_TOKEN_DENIED]
    reasons = []
    for e in denied:
        detail = e.get("detail") or {}
        if isinstance(detail, str):
            import json

            detail = json.loads(detail)
        reasons.append(detail.get("reason"))
    assert "invalid_client" in reasons
    assert "unsupported_grant_type" in reasons


@pytest.mark.asyncio
async def test_mint_rejects_scope_outside_supported(settings):
    """Scope values outside scopes_supported → 400 invalid_scope + audit (#1475)."""
    from daari.enterprise.postgres_audit import audit_log_from_settings
    from daari.gateway.mcp_oauth import AUDIT_TOKEN_DENIED

    settings.server.api_key = "secret-key"
    settings.integrations.mcp_oauth.protected_resource = True
    settings.integrations.mcp_oauth.local_as = True
    settings.integrations.mcp_oauth.scopes_supported = ["mcp"]
    app = _app(settings)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/oauth/token",
            data={
                "grant_type": "client_credentials",
                "client_secret": "secret-key",
                "scope": "admin",
            },
        )
    assert resp.status_code == 400
    body = resp.json()
    assert body["error"] == "invalid_scope"
    assert "access_token" not in body

    entries = audit_log_from_settings(settings).list(limit=50)
    denied = [e for e in entries if e.get("action") == AUDIT_TOKEN_DENIED]
    reasons = []
    for e in denied:
        detail = e.get("detail") or {}
        if isinstance(detail, str):
            import json

            detail = json.loads(detail)
        reasons.append(detail.get("reason"))
    assert "invalid_scope" in reasons


@pytest.mark.asyncio
async def test_verify_rejects_missing_or_wrong_scope(settings):
    """MCP ingress requires the mcp scope claim; wrong/missing → 403 + audit (#1475)."""
    import base64
    import hashlib
    import hmac
    import json
    import time

    from daari.enterprise.postgres_audit import audit_log_from_settings
    from daari.gateway.mcp_oauth import (
        AUDIT_TOKEN_DENIED,
        _MCP_OAUTH_ISS,
        _TOKEN_TYP,
        mint_access_token,
        signing_secret_for,
    )
    from daari.server.auth import AuthClaims

    settings.server.api_key = "secret-key"
    settings.integrations.mcp_oauth.protected_resource = True
    settings.integrations.mcp_oauth.local_as = True
    settings.integrations.mcp_oauth.scopes_supported = ["mcp", "openid"]
    settings.integrations.mcp_oauth.signing_secret = "unit-test-signing-secret"
    app = _app(settings)

    # Hand-craft a valid JWT with wrong scope (openid only — no mcp).
    now = int(time.time())
    payload = {
        "iss": _MCP_OAUTH_ISS,
        "aud": "mcp",
        "iat": now,
        "exp": now + 600,
        "scope": "openid",
        "typ": _TOKEN_TYP,
        "kind": "master",
        "jti": "wrong-scope-jti",
    }

    def _b64(raw: bytes) -> str:
        return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")

    header = _b64(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    body = _b64(json.dumps(payload, separators=(",", ":")).encode())
    secret = signing_secret_for(settings).encode()
    sig = hmac.new(secret, f"{header}.{body}".encode(), hashlib.sha256).digest()
    wrong_scope_token = f"{header}.{body}.{_b64(sig)}"

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        bad = await client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
            headers={"Authorization": f"Bearer {wrong_scope_token}"},
        )
        assert bad.status_code == 403

        # Valid mcp scope still works.
        good_token, _ = mint_access_token(
            settings, AuthClaims(kind="master"), scope="mcp"
        )
        ok = await client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
            headers={"Authorization": f"Bearer {good_token}"},
        )
        assert ok.status_code == 200

    entries = audit_log_from_settings(settings).list(limit=50)
    denied = [e for e in entries if e.get("action") == AUDIT_TOKEN_DENIED]
    reasons = []
    for e in denied:
        detail = e.get("detail") or {}
        if isinstance(detail, str):
            import json as _json

            detail = _json.loads(detail)
        reasons.append(detail.get("reason"))
    assert "insufficient_scope" in reasons


@pytest.mark.asyncio
async def test_revoke_then_verify_fails(settings):
    """POST /oauth/revoke denylists by jti; revoked tokens fail verification (#1475)."""
    from daari.enterprise.postgres_audit import audit_log_from_settings
    from daari.gateway.mcp_oauth import AUDIT_TOKEN_REVOKED

    settings.server.api_key = "secret-key"
    settings.integrations.mcp_oauth.protected_resource = True
    settings.integrations.mcp_oauth.local_as = True
    settings.integrations.mcp_oauth.token_ttl_seconds = 600
    app = _app(settings)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        token_resp = await client.post(
            "/oauth/token",
            data={
                "grant_type": "client_credentials",
                "client_secret": "secret-key",
                "scope": "mcp",
            },
        )
        assert token_resp.status_code == 200
        access = token_resp.json()["access_token"]

        ok = await client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
            headers={"Authorization": f"Bearer {access}"},
        )
        assert ok.status_code == 200

        revoke = await client.post("/oauth/revoke", data={"token": access})
        assert revoke.status_code == 200

        denied = await client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
            headers={"Authorization": f"Bearer {access}"},
        )
        assert denied.status_code == 401

    entries = audit_log_from_settings(settings).list(limit=50)
    revoked = [e for e in entries if e.get("action") == AUDIT_TOKEN_REVOKED]
    assert revoked, f"expected {AUDIT_TOKEN_REVOKED} in {entries!r}"


@pytest.mark.asyncio
async def test_as_metadata_advertises_revocation_endpoint(settings):
    """AS metadata includes revocation_endpoint (#1475)."""
    settings.integrations.mcp_oauth.protected_resource = True
    settings.integrations.mcp_oauth.local_as = True
    settings.integrations.mcp_oauth.resource = "http://test"
    app = _app(settings)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        as_doc = await client.get("/.well-known/oauth-authorization-server")
        assert as_doc.status_code == 200
        body = as_doc.json()
        assert body["revocation_endpoint"].endswith("/oauth/revoke")
