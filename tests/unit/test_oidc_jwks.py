"""Unit tests for OIDC JWKS SSO (issue #136) — verification pass 1/3."""

from __future__ import annotations

import json
import time

import pytest

from daari.enterprise.config import SsoSettings
from daari.enterprise.sso import (
    JwksCache,
    mint_dev_token,
    resolve_jwks_url,
    verify_access_token,
    verify_dev_token,
    verify_oidc_token,
)

jwt = pytest.importorskip("jwt")
from cryptography.hazmat.primitives.asymmetric import ec, rsa  # noqa: E402
from jwt.algorithms import ECAlgorithm, RSAAlgorithm  # noqa: E402


def _rsa_pair():
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public = private.public_key()
    jwk = json.loads(RSAAlgorithm.to_jwk(public))
    jwk["kid"] = "test-key-1"
    jwk["use"] = "sig"
    jwk["alg"] = "RS256"
    return private, {"keys": [jwk]}


def _ec_pair():
    private = ec.generate_private_key(ec.SECP256R1())
    public = private.public_key()
    jwk = json.loads(ECAlgorithm.to_jwk(public))
    jwk["kid"] = "ec-key-1"
    jwk["use"] = "sig"
    jwk["alg"] = "ES256"
    return private, {"keys": [jwk]}


def _mint_es256(private, *, issuer: str, audience: str = "", role: str = "admin", sub: str = "alice"):
    now = int(time.time())
    payload = {
        "sub": sub,
        "role": role,
        "iss": issuer,
        "iat": now,
        "exp": now + 3600,
    }
    if audience:
        payload["aud"] = audience
    return jwt.encode(payload, private, algorithm="ES256", headers={"kid": "ec-key-1"})


def _mint_rs256(private, *, issuer: str, audience: str = "", role: str = "admin", sub: str = "alice"):
    now = int(time.time())
    payload = {
        "sub": sub,
        "role": role,
        "iss": issuer,
        "iat": now,
        "exp": now + 3600,
    }
    if audience:
        payload["aud"] = audience
    return jwt.encode(payload, private, algorithm="RS256", headers={"kid": "test-key-1"})


def test_resolve_jwks_from_discovery():
    def http_get(url: str):
        assert url == "https://idp.example/.well-known/openid-configuration"
        return {"jwks_uri": "https://idp.example/jwks"}

    assert (
        resolve_jwks_url(discovery_url="https://idp.example/.well-known/openid-configuration", http_get=http_get)
        == "https://idp.example/jwks"
    )


def test_jwks_cache_ttl():
    calls = {"n": 0}

    def http_get(url: str):
        calls["n"] += 1
        return {"keys": [{"kid": "k", "kty": "RSA"}]}

    cache = JwksCache(ttl_seconds=60)
    cache.get("https://jwks", http_get=http_get)
    cache.get("https://jwks", http_get=http_get)
    assert calls["n"] == 1
    cache.get("https://jwks", http_get=http_get, force=True)
    assert calls["n"] == 2


def test_verify_oidc_rs256_round_trip():
    private, jwks = _rsa_pair()
    token = _mint_rs256(private, issuer="https://idp.example", audience="daari-admin", role="admin")
    claims = verify_oidc_token(
        token,
        issuer="https://idp.example",
        audience="daari-admin",
        jwks=jwks,
    )
    assert claims["sub"] == "alice"
    assert claims["role"] == "admin"


def test_verify_oidc_rejects_bad_issuer():
    private, jwks = _rsa_pair()
    token = _mint_rs256(private, issuer="https://evil.example")
    with pytest.raises(Exception):
        verify_oidc_token(token, issuer="https://idp.example", jwks=jwks)


def test_verify_access_token_prefers_oidc_over_hmac():
    private, jwks = _rsa_pair()
    token = _mint_rs256(private, issuer="https://idp.example", role="analyst")
    sso = SsoSettings(
        enabled=True,
        issuer="https://idp.example",
        secret="should-not-be-used",
        jwks_url="https://idp.example/jwks",
    )
    claims = verify_access_token(token, sso, jwks=jwks)
    assert claims["role"] == "analyst"


def test_verify_access_token_falls_back_to_hmac():
    sso = SsoSettings(enabled=True, issuer="daari-dev", secret="sekret")
    token = mint_dev_token(subject="bob", role="admin", secret="sekret")
    claims = verify_access_token(token, sso)
    assert claims["sub"] == "bob"
    assert verify_dev_token(token, secret="sekret")["sub"] == "bob"


def test_verify_oidc_es256_round_trip():
    private, jwks = _ec_pair()
    token = _mint_es256(private, issuer="https://idp.example", audience="daari-admin")
    claims = verify_oidc_token(
        token,
        issuer="https://idp.example",
        audience="daari-admin",
        jwks=jwks,
    )
    assert claims["sub"] == "alice"
    assert claims["role"] == "admin"


def test_verify_oidc_rejects_unsupported_kty():
    private, jwks = _rsa_pair()
    token = _mint_rs256(private, issuer="https://idp.example")
    jwks["keys"][0]["kty"] = "oct"
    with pytest.raises(ValueError, match="oct"):
        verify_oidc_token(token, issuer="https://idp.example", jwks=jwks)


def test_jwk_prefers_sig_when_mixed_with_enc():
    private, jwks = _rsa_pair()
    sig = dict(jwks["keys"][0])
    enc = dict(jwks["keys"][0])
    enc["kid"] = "enc-key"
    enc["use"] = "enc"
    token = jwt.encode(
        {
            "sub": "alice",
            "iss": "https://idp.example",
            "iat": int(time.time()),
            "exp": int(time.time()) + 3600,
        },
        private,
        algorithm="RS256",
    )
    claims = verify_oidc_token(
        token,
        issuer="https://idp.example",
        jwks={"keys": [enc, sig]},
    )
    assert claims["sub"] == "alice"
