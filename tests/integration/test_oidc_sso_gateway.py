"""Integration: SSO session + config editor with OIDC JWT (issue #136).

Verification pass 2/3.
"""

from __future__ import annotations

import json
import time

import pytest
from httpx import ASGITransport, AsyncClient

jwt = pytest.importorskip("jwt")


def _rsa_pair():
    from cryptography.hazmat.primitives.asymmetric import rsa
    from jwt.algorithms import RSAAlgorithm

    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    jwk = json.loads(RSAAlgorithm.to_jwk(private.public_key()))
    jwk["kid"] = "int-key"
    jwk["alg"] = "RS256"
    return private, {"keys": [jwk]}


def _token(private, *, issuer: str, role: str = "admin", sub: str = "carol"):
    now = int(time.time())
    return jwt.encode(
        {
            "sub": sub,
            "role": role,
            "iss": issuer,
            "iat": now,
            "exp": now + 3600,
            "aud": "daari-admin",
        },
        private,
        algorithm="RS256",
        headers={"kid": "int-key"},
    )


@pytest.mark.asyncio
async def test_sso_session_and_config_with_oidc(settings, monkeypatch, tmp_path):
    from daari.enterprise.sso import verify_oidc_token
    from daari.router.router import AppContext
    from daari.server.app import create_app

    private, jwks = _rsa_pair()
    issuer = "https://idp.test"
    settings.observability.config_editor = True
    settings.enterprise.sso.enabled = True
    settings.enterprise.sso.issuer = issuer
    settings.enterprise.sso.audience = "daari-admin"
    settings.enterprise.sso.jwks_url = "https://idp.test/jwks"
    settings.enterprise.sso.mint_virtual_key_on_login = True
    settings.server.virtual_keys.enabled = True
    settings.server.virtual_keys.path = str(tmp_path / "keys.sqlite3")
    settings.enterprise.audit_path = str(tmp_path / "audit.sqlite3")

    import daari.enterprise.sso as sso_mod

    real_verify = sso_mod.verify_access_token

    def patched_verify(token, sso, **kwargs):
        kwargs.setdefault("jwks", jwks)
        return real_verify(token, sso, **kwargs)

    monkeypatch.setattr(sso_mod, "verify_access_token", patched_verify)

    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    token = _token(private, issuer=issuer)

    claims = verify_oidc_token(
        token, issuer=issuer, audience="daari-admin", jwks=jwks
    )
    assert claims["sub"] == "carol"

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        denied = await client.get("/v1/daari/config")
        assert denied.status_code == 401

        session = await client.post(
            "/v1/daari/sso/session",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert session.status_code == 200
        body = session.json()
        assert body["sub"] == "carol"
        assert body["virtual_key_minted"] is True
        assert body["virtual_key"].startswith("dk_")

        ok = await client.get(
            "/v1/daari/config",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert ok.status_code == 200
        assert "routing" in ok.json()

        again = await client.post(
            "/v1/daari/sso/session",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert again.json()["virtual_key_minted"] is False
        assert again.json()["virtual_key_id"] == body["virtual_key_id"]


@pytest.mark.asyncio
async def test_sso_rbac_role_matrix_for_admin_surfaces(settings, monkeypatch, tmp_path):
    """user: 403 read+mutate; analyst: 200 read / 403 mutate; admin: 200 both (#555/#572)."""
    from daari.router.router import AppContext
    from daari.server.app import create_app

    private, jwks = _rsa_pair()
    issuer = "https://idp.test"
    settings.observability.config_editor = True
    settings.enterprise.sso.enabled = True
    settings.enterprise.sso.issuer = issuer
    settings.enterprise.sso.audience = "daari-admin"
    settings.enterprise.sso.jwks_url = "https://idp.test/jwks"
    settings.enterprise.audit_path = str(tmp_path / "audit.sqlite3")

    import daari.enterprise.sso as sso_mod

    real_verify = sso_mod.verify_access_token

    def patched_verify(token, sso, **kwargs):
        kwargs.setdefault("jwks", jwks)
        return real_verify(token, sso, **kwargs)

    monkeypatch.setattr(sso_mod, "verify_access_token", patched_verify)

    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    app.state.ctx.org_learning_client = object()

    async def fake_sync() -> bool:
        return False

    monkeypatch.setattr(app.state.ctx, "sync_org_learning_profile_once", fake_sync)
    monkeypatch.setattr(
        app.state.ctx,
        "reload_cache_handles",
        lambda: {"reloaded": True, "l0_path": "/tmp/l0", "l1_path": "/tmp/l1", "ccs_path": "/tmp/ccs"},
    )

    user_tok = _token(private, issuer=issuer, role="user", sub="u1")
    analyst_tok = _token(private, issuer=issuer, role="analyst", sub="a1")
    admin_tok = _token(private, issuer=issuer, role="admin", sub="adm")

    read_paths = (
        "/v1/daari/stats",
        "/v1/daari/traces",
        "/v1/daari/report",
        "/v1/daari/audit",
        "/v1/daari/config",
    )
    mutate_paths = (
        ("POST", "/v1/daari/reload-caches"),
        ("PATCH", "/v1/daari/config"),
        ("POST", "/v1/org-learning/sync"),
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:

        async def _get(path: str, token: str):
            return await client.get(path, headers={"Authorization": f"Bearer {token}"})

        async def _mutate(method: str, path: str, token: str):
            headers = {"Authorization": f"Bearer {token}"}
            if method == "POST":
                return await client.post(path, headers=headers)
            return await client.patch(path, headers=headers, json={})

        for path in read_paths:
            assert (await _get(path, user_tok)).status_code == 403, path
        for method, path in mutate_paths:
            assert (await _mutate(method, path, user_tok)).status_code == 403, path

        for path in read_paths:
            assert (await _get(path, analyst_tok)).status_code == 200, path
        for method, path in mutate_paths:
            assert (await _mutate(method, path, analyst_tok)).status_code == 403, path

        for path in read_paths:
            assert (await _get(path, admin_tok)).status_code == 200, path
        for method, path in mutate_paths:
            assert (await _mutate(method, path, admin_tok)).status_code == 200, path
