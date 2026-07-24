"""OIDC helpers for admin surfaces (issue #119).

Tracer-bullet: validate an ID/access token against a configured issuer JWKS
when `enterprise.sso.enabled`. Without cryptography extras, falls back to a
shared HMAC secret for local/dev SSO stubs.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from typing import Any


def _b64url_decode(raw: str) -> bytes:
    padding = "=" * (-len(raw) % 4)
    return base64.urlsafe_b64decode(raw + padding)


def decode_jwt_unverified(token: str) -> dict[str, Any]:
    parts = token.split(".")
    if len(parts) != 3:
        raise ValueError("not a JWT")
    return json.loads(_b64url_decode(parts[1]))


def mint_dev_token(
    *,
    subject: str,
    role: str = "user",
    secret: str,
    ttl_seconds: int = 3600,
    issuer: str = "daari-dev",
) -> str:
    """Mint a signed HS256 token for local SSO testing (not for production IdPs)."""
    header = base64.urlsafe_b64encode(json.dumps({"alg": "HS256", "typ": "JWT"}).encode()).rstrip(
        b"="
    )
    now = int(time.time())
    payload = {
        "sub": subject,
        "role": role,
        "iss": issuer,
        "iat": now,
        "exp": now + ttl_seconds,
    }
    body = base64.urlsafe_b64encode(json.dumps(payload).encode()).rstrip(b"=")
    signing_input = header + b"." + body
    sig = hmac.new(secret.encode(), signing_input, hashlib.sha256).digest()
    return (signing_input + b"." + base64.urlsafe_b64encode(sig).rstrip(b"=")).decode()


def verify_dev_token(token: str, *, secret: str, issuer: str = "daari-dev") -> dict[str, Any]:
    parts = token.split(".")
    if len(parts) != 3:
        raise ValueError("not a JWT")
    signing_input = f"{parts[0]}.{parts[1]}".encode()
    expected = hmac.new(secret.encode(), signing_input, hashlib.sha256).digest()
    actual = _b64url_decode(parts[2])
    if not hmac.compare_digest(expected, actual):
        raise ValueError("bad signature")
    claims = json.loads(_b64url_decode(parts[1]))
    if claims.get("iss") != issuer:
        raise ValueError("bad issuer")
    if int(claims.get("exp", 0)) < int(time.time()):
        raise ValueError("expired")
    return claims
