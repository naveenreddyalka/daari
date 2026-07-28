#!/usr/bin/env python3
"""Live/smoke verification for OIDC SSO (issue #136) — pass 3/3.

In-process ASGI app with a local RSA key + JWKS (no external IdP required).

Usage:
  python scripts/smoke_oidc_sso.py
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


async def main() -> int:
    import tempfile

    import jwt
    from cryptography.hazmat.primitives.asymmetric import rsa
    from httpx import ASGITransport, AsyncClient
    from jwt.algorithms import RSAAlgorithm

    from daari.config.settings import Settings
    from daari.enterprise.sso import verify_access_token
    from daari.router.router import AppContext
    from daari.server.app import create_app

    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    jwk = json.loads(RSAAlgorithm.to_jwk(private.public_key()))
    jwk["kid"] = "smoke-key"
    jwk["alg"] = "RS256"
    jwks = {"keys": [jwk]}
    issuer = "https://smoke-idp.local"
    now = int(time.time())
    token = jwt.encode(
        {
            "sub": "smoke-user",
            "role": "admin",
            "iss": issuer,
            "aud": "daari-admin",
            "iat": now,
            "exp": now + 3600,
        },
        private,
        algorithm="RS256",
        headers={"kid": "smoke-key"},
    )

    tmp = Path(tempfile.mkdtemp(prefix="daari-oidc-smoke-"))
    settings = Settings()
    settings.observability.config_editor = True
    settings.enterprise.sso.enabled = True
    settings.enterprise.sso.issuer = issuer
    settings.enterprise.sso.audience = "daari-admin"
    settings.enterprise.sso.jwks_url = "https://smoke-idp.local/jwks"
    settings.enterprise.sso.mint_virtual_key_on_login = True
    settings.server.virtual_keys.enabled = True
    settings.server.virtual_keys.path = str(tmp / "keys.sqlite3")
    settings.enterprise.audit_path = str(tmp / "audit.sqlite3")

    import daari.enterprise.sso as sso_mod

    real = sso_mod.verify_access_token

    def patched(tok, sso, **kwargs):
        kwargs.setdefault("jwks", jwks)
        return real(tok, sso, **kwargs)

    sso_mod.verify_access_token = patched  # type: ignore[assignment]

    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    headers = {"Authorization": f"Bearer {token}"}

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://smoke") as http:
        health = await http.get("/health")
        session = await http.post("/v1/daari/sso/session", headers=headers)
        config = await http.get("/v1/daari/config", headers=headers)
        forbidden = await http.get(
            "/v1/daari/config",
            headers={"Authorization": "Bearer not-a-jwt"},
        )

    print(f"health={health.status_code}")
    print(f"session={session.status_code} minted={session.json().get('virtual_key_minted')}")
    print(f"config={config.status_code} prefer={config.json().get('routing', {}).get('prefer')}")
    print(f"forbidden={forbidden.status_code}")

    claims = verify_access_token(token, settings.enterprise.sso, jwks=jwks)
    print(f"claims_sub={claims.get('sub')}")

    ok = (
        health.status_code == 200
        and session.status_code == 200
        and session.json().get("virtual_key_minted") is True
        and config.status_code == 200
        and forbidden.status_code == 401
        and claims.get("sub") == "smoke-user"
    )
    print("PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
