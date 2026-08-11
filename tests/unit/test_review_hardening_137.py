"""Frontier review of the Auto-mode deepeners (issue #137).

Each test pins a defect found reviewing code that shipped without a deep
review pass: fail-open policy signatures, plaintext policy transport, a D4
proposal that read the wrong stats schema, world-readable config writes,
JWKS rotation lockout, and 500s on malformed config PATCH bodies.
"""

from __future__ import annotations

import json
import stat
import time

import pytest
import yaml
from httpx import ASGITransport, AsyncClient

from daari.config.persist import persist_safe_config
from daari.enterprise.policy_sync import sync_policy_once
from daari.learning.propose_defaults import propose_routing_defaults
from daari.router.router import AppContext
from daari.server.app import create_app

jwt = pytest.importorskip("jwt")
from cryptography.hazmat.primitives.asymmetric import rsa  # noqa: E402
from jwt.algorithms import RSAAlgorithm  # noqa: E402

from daari.enterprise.sso import JwksCache, verify_oidc_token  # noqa: E402


# --- policy sync: signature + transport ------------------------------------


def _fetch_stub(calls: dict[str, int], payload: dict | None = None):
    def fake_fetch(url: str, *, token: str = "", timeout: float = 10.0):
        calls["n"] = calls.get("n", 0) + 1
        body = payload if payload is not None else {"routing": {"prefer": "cost"}}
        return body, json.dumps(body).encode(), ""

    return fake_fetch


def test_policy_sync_refuses_unsigned_config(settings, monkeypatch):
    """No signing secret must fail closed, not silently apply remote config."""
    calls: dict[str, int] = {}
    monkeypatch.setattr(
        "daari.enterprise.policy_sync.fetch_org_config", _fetch_stub(calls)
    )
    settings.enterprise.policy_sync_url = "https://policy.example/config.json"
    settings.enterprise.config_signing_secret = ""

    result = sync_policy_once(settings, None)

    assert result["ok"] is False
    assert result["reason"] == "no_signing_secret"
    assert calls.get("n", 0) == 0, "must not fetch before refusing"


def test_policy_sync_refuses_plaintext_url(settings, monkeypatch):
    calls: dict[str, int] = {}
    monkeypatch.setattr(
        "daari.enterprise.policy_sync.fetch_org_config", _fetch_stub(calls)
    )
    settings.enterprise.policy_sync_url = "http://policy.example/config.json"
    settings.enterprise.config_signing_secret = "shared-secret"

    result = sync_policy_once(settings, None)

    assert result["ok"] is False
    assert result["reason"] == "insecure_url"
    assert calls.get("n", 0) == 0


def test_policy_sync_allows_plaintext_loopback(settings, monkeypatch):
    """Local dev against 127.0.0.1 stays usable."""
    calls: dict[str, int] = {}
    monkeypatch.setattr(
        "daari.enterprise.policy_sync.fetch_org_config", _fetch_stub(calls)
    )
    monkeypatch.setattr(
        "daari.enterprise.policy_sync.verify_signature", lambda *_a, **_k: True
    )
    settings.enterprise.policy_sync_url = "http://127.0.0.1:9000/config.json"
    settings.enterprise.config_signing_secret = "shared-secret"

    result = sync_policy_once(settings, None)

    assert result["ok"] is True
    assert calls["n"] == 1


def test_policy_sync_insecure_flag_still_bypasses(settings, monkeypatch):
    """`insecure=True` is the documented escape hatch and must keep working."""
    calls: dict[str, int] = {}
    monkeypatch.setattr(
        "daari.enterprise.policy_sync.fetch_org_config", _fetch_stub(calls)
    )
    settings.enterprise.policy_sync_url = "http://policy.example/config.json"
    settings.enterprise.config_signing_secret = ""

    result = sync_policy_once(settings, None, insecure=True)

    assert result["ok"] is True
    assert calls["n"] == 1


def test_policy_sync_survives_malformed_values(settings, monkeypatch):
    """A bad remote value must not abort the sync with a raw ValueError."""
    calls: dict[str, int] = {}
    monkeypatch.setattr(
        "daari.enterprise.policy_sync.fetch_org_config",
        _fetch_stub(calls, {"cache": {"l1_ttl_seconds": "not-a-number"}}),
    )
    monkeypatch.setattr(
        "daari.enterprise.policy_sync.verify_signature", lambda *_a, **_k: True
    )
    settings.enterprise.policy_sync_url = "https://policy.example/config.json"
    settings.enterprise.config_signing_secret = "shared-secret"
    ctx = AppContext.from_settings(settings)

    result = sync_policy_once(settings, ctx.router)

    assert result["ok"] is True
    assert "cache.l1_ttl_seconds" not in result["applied"]


# --- D4 proposal: real export-stats schema --------------------------------


def test_propose_defaults_reads_collective_stats_schema(tmp_path):
    """`build_collective_stats` nests category -> tier -> counts, with no
    accept_rate/n keys. The proposer must derive both instead of skipping."""
    stats = {
        "categories": {
            "code": {
                "L3": {"outcomes": 60, "accepts": 57, "rejects": 3},
                "L5": {"outcomes": 10, "accepts": 9, "rejects": 1},
            },
            "chat": {"L3": {"outcomes": 40, "accepts": 10, "rejects": 30}},
            "sparse": {"L3": {"outcomes": 5, "accepts": 5, "rejects": 0}},
        }
    }

    path = propose_routing_defaults(stats, out_dir=tmp_path)
    proposal = yaml.safe_load(path.read_text(encoding="utf-8"))
    policies = proposal["routing"]["category_policies"]

    assert policies["code"] == {"tier": "L3"}
    assert policies["chat"] == {"tier": "L5"}
    assert "sparse" not in policies, "below the 20-sample floor"


def test_propose_defaults_still_reads_flat_schema(tmp_path):
    path = propose_routing_defaults(
        {"by_category": {"code": {"accept_rate": 0.95, "n": 100}}}, out_dir=tmp_path
    )
    proposal = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert proposal["routing"]["category_policies"]["code"] == {"tier": "L3"}


# --- config persistence ----------------------------------------------------


def test_persist_safe_config_is_owner_only(tmp_path):
    """~/.daari/config.yaml sits alongside provider keys — never world-readable."""
    cfg = tmp_path / "config.yaml"
    persist_safe_config({"routing": {"prefer": "cost"}}, config_path=cfg)
    assert stat.S_IMODE(cfg.stat().st_mode) == 0o600


def test_persist_safe_config_leaves_no_temp_files(tmp_path):
    cfg = tmp_path / "config.yaml"
    persist_safe_config({"routing": {"prefer": "cost"}}, config_path=cfg)
    assert [p.name for p in tmp_path.iterdir()] == ["config.yaml"]


def test_persist_safe_config_preserves_unrelated_sections(tmp_path):
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        "frontier:\n  api_key: sk-do-not-drop\nserver:\n  api_key: keep-me\n",
        encoding="utf-8",
    )
    persist_safe_config({"routing": {"prefer": "cost"}}, config_path=cfg)
    text = cfg.read_text(encoding="utf-8")
    assert "sk-do-not-drop" in text
    assert "keep-me" in text


# --- JWKS rotation ---------------------------------------------------------


def _rsa_pair(kid: str):
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    jwk = json.loads(RSAAlgorithm.to_jwk(private.public_key()))
    jwk.update({"kid": kid, "use": "sig", "alg": "RS256"})
    return private, {"keys": [jwk]}


def test_jwks_refetches_on_unknown_kid():
    """After an IdP key rotation the cached JWKS is stale; a cache miss on kid
    must force one refetch instead of locking admins out for the whole TTL."""
    _, old_jwks = _rsa_pair("old-key")
    new_private, new_jwks = _rsa_pair("new-key")
    now = int(time.time())
    token = jwt.encode(
        {"sub": "alice", "role": "admin", "iss": "https://idp.example", "exp": now + 3600},
        new_private,
        algorithm="RS256",
        headers={"kid": "new-key"},
    )
    served = {"doc": old_jwks, "n": 0}

    def http_get(url: str):
        served["n"] += 1
        return served["doc"]

    cache = JwksCache(ttl_seconds=3600)
    cache.get("https://idp.example/jwks", http_get=http_get)
    served["doc"] = new_jwks

    claims = verify_oidc_token(
        token,
        issuer="https://idp.example",
        jwks_url="https://idp.example/jwks",
        http_get=http_get,
        jwks_cache=cache,
    )

    assert claims["sub"] == "alice"
    assert served["n"] == 2, "expected exactly one forced refetch"


def test_jwks_unknown_kid_refetch_happens_once():
    """A genuinely unknown kid must still fail, without hammering the IdP."""
    _, old_jwks = _rsa_pair("old-key")
    other_private, _ = _rsa_pair("ghost-key")
    now = int(time.time())
    token = jwt.encode(
        {"sub": "alice", "iss": "https://idp.example", "exp": now + 3600},
        other_private,
        algorithm="RS256",
        headers={"kid": "ghost-key"},
    )
    served = {"n": 0}

    def http_get(url: str):
        served["n"] += 1
        return old_jwks

    cache = JwksCache(ttl_seconds=3600)
    with pytest.raises(ValueError):
        verify_oidc_token(
            token,
            issuer="https://idp.example",
            jwks_url="https://idp.example/jwks",
            http_get=http_get,
            jwks_cache=cache,
        )
    assert served["n"] == 2


# --- config editor input validation ---------------------------------------


@pytest.mark.asyncio
async def test_config_patch_rejects_non_numeric(settings):
    settings.observability.config_editor = True
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.patch(
            "/v1/daari/config",
            json={"routing": {"confidence_threshold": "not-a-number"}},
        )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_config_patch_rejects_out_of_range_threshold(settings):
    settings.observability.config_editor = True
    settings.routing.confidence_threshold = 0.7
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.patch(
            "/v1/daari/config", json={"routing": {"confidence_threshold": 42}}
        )
    assert response.status_code == 400
    assert app.state.ctx.router.confidence_threshold == 0.7


@pytest.mark.asyncio
async def test_config_patch_rejects_invalid_boundaries_mode(settings):
    settings.observability.config_editor = True
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.patch(
            "/v1/daari/config", json={"boundaries": {"mode": "bogus"}}
        )
    assert response.status_code == 400
