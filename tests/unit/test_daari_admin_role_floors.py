"""Role floors on previously ungated /v1/daari read + feedback surfaces (#1588)."""

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
    jwk["kid"] = "role-floor-key"
    jwk["alg"] = "RS256"
    return private, {"keys": [jwk]}


def _token(private, *, issuer: str, role: str, sub: str = "sub1") -> str:
    now = int(time.time())
    return jwt.encode(
        {
            "iss": issuer,
            "aud": "daari-admin",
            "sub": sub,
            "role": role,
            "iat": now,
            "exp": now + 3600,
        },
        private,
        algorithm="RS256",
        headers={"kid": "role-floor-key"},
    )


@pytest.mark.asyncio
async def test_ungated_daari_surfaces_require_analyst_when_sso_on(
    settings, monkeypatch, tmp_path
):
    from daari.auth.virtual_keys import VirtualKeyStore
    from daari.router.router import AppContext
    from daari.server.app import create_app

    private, jwks = _rsa_pair()
    issuer = "https://idp.role-floor.test"
    settings.server.api_key = "master-secret"
    settings.enterprise.sso.enabled = True
    settings.enterprise.sso.issuer = issuer
    settings.enterprise.sso.audience = "daari-admin"
    settings.enterprise.sso.jwks_url = "https://idp.role-floor.test/jwks"
    settings.server.virtual_keys.enabled = True
    settings.server.virtual_keys.path = str(tmp_path / "vk.sqlite3")
    settings.enterprise.audit_path = str(tmp_path / "audit.sqlite3")

    import daari.enterprise.sso as sso_mod

    real_verify = sso_mod.verify_access_token

    def patched_verify(token, sso, **kwargs):
        kwargs.setdefault("jwks", jwks)
        return real_verify(token, sso, **kwargs)

    monkeypatch.setattr(sso_mod, "verify_access_token", patched_verify)

    store = VirtualKeyStore(settings.virtual_keys_path)
    vk = store.create("plain")
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    app.state.virtual_key_store = store
    app.state.ctx.virtual_key_store = store

    user_tok = _token(private, issuer=issuer, role="user")
    analyst_tok = _token(private, issuer=issuer, role="analyst")
    admin_tok = _token(private, issuer=issuer, role="admin")

    read_gets = (
        "/v1/daari/route/preview",
        "/v1/daari/cache/diversity",
        "/v1/daari/learn/stats",
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Plain virtual key is not an SSO analyst — JWT verify fails → 401.
        for path in read_gets:
            resp = await client.get(
                path, headers={"Authorization": f"Bearer {vk.plaintext}"}
            )
            assert resp.status_code in {401, 403}, path

        fb_vk = await client.post(
            "/v1/daari/feedback",
            headers={"Authorization": f"Bearer {vk.plaintext}"},
            json={"trace_id": "t1", "signal": "accept"},
        )
        assert fb_vk.status_code in {401, 403}

        for path in read_gets:
            assert (
                await client.get(path, headers={"Authorization": f"Bearer {user_tok}"})
            ).status_code == 403, path
        assert (
            await client.post(
                "/v1/daari/route/preview",
                headers={"Authorization": f"Bearer {user_tok}"},
                json={"prompt": "hi"},
            )
        ).status_code == 403
        assert (
            await client.post(
                "/v1/daari/feedback",
                headers={"Authorization": f"Bearer {user_tok}"},
                json={"trace_id": "t1", "signal": "accept"},
            )
        ).status_code == 403

        for path in read_gets:
            assert (
                await client.get(
                    path, headers={"Authorization": f"Bearer {analyst_tok}"}
                )
            ).status_code == 200, path
        assert (
            await client.post(
                "/v1/daari/route/preview",
                headers={"Authorization": f"Bearer {analyst_tok}"},
                json={"prompt": "hi"},
            )
        ).status_code == 200
        # No outcome for the trace → 404 after role gate (role check passed).
        fb_analyst = await client.post(
            "/v1/daari/feedback",
            headers={"Authorization": f"Bearer {analyst_tok}"},
            json={"trace_id": "missing-trace", "signal": "accept"},
        )
        assert fb_analyst.status_code == 404

        for path in read_gets:
            assert (
                await client.get(path, headers={"Authorization": f"Bearer {admin_tok}"})
            ).status_code == 200, path


@pytest.mark.asyncio
async def test_sso_off_virtual_key_still_viewer_style_on_new_floors(settings, tmp_path):
    """SSO-off convention: analyst minimum stays open for virtual keys (#1588)."""
    from daari.auth.virtual_keys import VirtualKeyStore
    from daari.router.router import AppContext
    from daari.server.app import create_app

    settings.server.api_key = "master-secret"
    settings.enterprise.sso.enabled = False
    settings.server.virtual_keys.enabled = True
    settings.server.virtual_keys.path = str(tmp_path / "vk.sqlite3")
    store = VirtualKeyStore(settings.virtual_keys_path)
    vk = store.create("viewer")
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    app.state.virtual_key_store = store
    app.state.ctx.virtual_key_store = store

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        headers = {"Authorization": f"Bearer {vk.plaintext}"}
        assert (await client.get("/v1/daari/route/preview", headers=headers)).status_code == 200
        assert (await client.get("/v1/daari/cache/diversity", headers=headers)).status_code == 200
        assert (await client.get("/v1/daari/learn/stats", headers=headers)).status_code == 200


def test_auth_and_keys_docs_list_new_role_floors() -> None:
    from pathlib import Path

    text = Path("docs/developer/guides/configuration/auth-and-keys.md").read_text(
        encoding="utf-8"
    )
    assert "/v1/daari/route/preview" in text
    assert "/v1/daari/cache/diversity" in text
    assert "/v1/daari/learn/stats" in text
    assert "/v1/daari/feedback" in text
