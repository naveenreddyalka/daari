"""OIDC / SSO helpers for admin surfaces (issues #119, #136).

- Dev stub: HS256 HMAC via `enterprise.sso.secret` (local only).
- Production: OIDC access/ID tokens verified against issuer JWKS
  (`enterprise.sso.jwks_url` or OIDC discovery). Requires optional
  `daari[oidc]` (PyJWT[crypto]).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from typing import Any, Callable

import httpx

HttpGet = Callable[[str], dict[str, Any]]


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


def _default_http_get(url: str) -> dict[str, Any]:
    with httpx.Client(timeout=10.0) as client:
        response = client.get(url)
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict):
            raise ValueError(f"expected JSON object from {url}")
        return data


def resolve_jwks_url(
    *,
    jwks_url: str = "",
    discovery_url: str = "",
    http_get: HttpGet | None = None,
) -> str:
    """Return an explicit JWKS URL or discover it from OIDC metadata."""
    if jwks_url.strip():
        return jwks_url.strip()
    if not discovery_url.strip():
        raise ValueError("SSO requires jwks_url or discovery_url")
    getter = http_get or _default_http_get
    meta = getter(discovery_url.strip())
    uri = meta.get("jwks_uri") or meta.get("jwks_url")
    if not isinstance(uri, str) or not uri.strip():
        raise ValueError("OIDC discovery document missing jwks_uri")
    return uri.strip()


class JwksCache:
    """Process-local JWKS cache with TTL."""

    def __init__(self, ttl_seconds: float = 3600.0) -> None:
        self.ttl_seconds = ttl_seconds
        self._by_url: dict[str, tuple[float, dict[str, Any]]] = {}

    def get(self, url: str, *, http_get: HttpGet | None = None, force: bool = False) -> dict[str, Any]:
        now = time.time()
        if not force and url in self._by_url:
            fetched_at, payload = self._by_url[url]
            if (now - fetched_at) < self.ttl_seconds:
                return payload
        getter = http_get or _default_http_get
        payload = getter(url)
        if "keys" not in payload or not isinstance(payload["keys"], list):
            raise ValueError("JWKS document missing keys[]")
        self._by_url[url] = (now, payload)
        return payload


_JWKS_CACHE = JwksCache()


def _jwk_for_token(token: str, jwks: dict[str, Any]) -> dict[str, Any]:
    try:
        import jwt
    except ImportError as exc:
        raise RuntimeError(
            "OIDC JWKS verification requires PyJWT[crypto] — pip install 'daari[oidc]'"
        ) from exc
    header = jwt.get_unverified_header(token)
    kid = header.get("kid")
    keys = jwks.get("keys") or []
    if kid:
        for key in keys:
            if isinstance(key, dict) and key.get("kid") == kid:
                return key
        raise ValueError(f"no JWK matching kid={kid}")
    if len(keys) == 1 and isinstance(keys[0], dict):
        return keys[0]
    raise ValueError("JWT missing kid and JWKS has multiple keys")


def verify_oidc_token(
    token: str,
    *,
    issuer: str,
    audience: str = "",
    jwks_url: str = "",
    discovery_url: str = "",
    jwks: dict[str, Any] | None = None,
    http_get: HttpGet | None = None,
    jwks_cache: JwksCache | None = None,
) -> dict[str, Any]:
    """Verify a JWT against the issuer JWKS (RS256 / ES256 via PyJWT)."""
    try:
        import jwt
        from jwt.algorithms import RSAAlgorithm
    except ImportError as exc:
        raise RuntimeError(
            "OIDC JWKS verification requires PyJWT[crypto] — pip install 'daari[oidc]'"
        ) from exc

    if jwks is None:
        url = resolve_jwks_url(jwks_url=jwks_url, discovery_url=discovery_url, http_get=http_get)
        cache = jwks_cache or _JWKS_CACHE
        jwks = cache.get(url, http_get=http_get)

    jwk = _jwk_for_token(token, jwks)
    public_key = RSAAlgorithm.from_jwk(json.dumps(jwk))
    options: dict[str, Any] = {"require": ["exp", "iss"]}
    decode_kwargs: dict[str, Any] = {
        "algorithms": ["RS256", "RS384", "RS512"],
        "issuer": issuer,
        "options": options,
    }
    if audience.strip():
        decode_kwargs["audience"] = audience.strip()
    else:
        options["verify_aud"] = False
    return jwt.decode(token, key=public_key, **decode_kwargs)


def verify_access_token(
    token: str,
    sso: Any,
    *,
    http_get: HttpGet | None = None,
    jwks_cache: JwksCache | None = None,
    jwks: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Unified verifier: OIDC JWKS when configured, else HMAC dev stub."""
    jwks_url = str(getattr(sso, "jwks_url", "") or "")
    discovery_url = str(getattr(sso, "discovery_url", "") or "")
    if jwks is not None or jwks_url.strip() or discovery_url.strip():
        return verify_oidc_token(
            token,
            issuer=str(getattr(sso, "issuer", "") or ""),
            audience=str(getattr(sso, "audience", "") or ""),
            jwks_url=jwks_url,
            discovery_url=discovery_url,
            jwks=jwks,
            http_get=http_get,
            jwks_cache=jwks_cache,
        )
    secret = str(getattr(sso, "secret", "") or "")
    if not secret:
        raise ValueError("SSO enabled but neither jwks_url/discovery_url nor secret configured")
    return verify_dev_token(
        token,
        secret=secret,
        issuer=str(getattr(sso, "issuer", "") or "daari-dev"),
    )
