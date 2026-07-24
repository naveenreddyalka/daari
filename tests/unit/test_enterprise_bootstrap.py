"""F4 fleet bootstrap + SSO/RBAC tracers (issues #118, #119)."""

from __future__ import annotations

import hashlib
import hmac
import json

import httpx
import pytest
import yaml

from daari.enterprise.audit import AuditLog
from daari.enterprise.bootstrap import apply_org_config, verify_signature
from daari.enterprise.rbac import role_at_least
from daari.enterprise.sso import mint_dev_token, verify_dev_token


def test_verify_signature():
    body = b'{"org":{"id":"acme"}}'
    secret = "s3cret"
    sig = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    assert verify_signature(body, sig, secret)
    assert not verify_signature(body, "deadbeef", secret)


def test_apply_org_config(tmp_path):
    path = tmp_path / "config.yaml"
    out = apply_org_config(
        {
            "org": {
                "org_id": "acme",
                "shared_cache_url": "http://cache",
            },
            "routing": {"org_pool": {"enabled": True, "base_url": "http://pool"}},
        },
        config_path=path,
        device_id="laptop-1",
    )
    data = yaml.safe_load(out.read_text())
    assert data["enterprise"]["org_id"] == "acme"
    assert data["enterprise"]["device_id"] == "laptop-1"
    assert data["routing"]["org_pool"]["base_url"] == "http://pool"


def test_sso_dev_token_roundtrip():
    token = mint_dev_token(subject="alice", role="admin", secret="x")
    claims = verify_dev_token(token, secret="x")
    assert claims["sub"] == "alice"
    assert claims["role"] == "admin"
    assert role_at_least(claims["role"], "admin")


def test_audit_log(tmp_path):
    log = AuditLog(tmp_path / "audit.sqlite3")
    log.record(actor="alice", role="admin", action="config.patch", detail={"k": 1})
    entries = log.list()
    assert entries[0]["actor"] == "alice"
    assert entries[0]["detail"]["k"] == 1


@pytest.mark.asyncio
async def test_fetch_org_config_header(monkeypatch):
    from daari.enterprise.bootstrap import fetch_org_config

    payload = {"org": {"org_id": "x"}}
    raw = json.dumps(payload).encode()
    sig = hmac.new(b"sek", raw, hashlib.sha256).hexdigest()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=raw, headers={"X-Daari-Signature": sig})

    class Patched(httpx.Client):
        def __init__(self, *args, **kwargs):
            kwargs["transport"] = httpx.MockTransport(handler)
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(httpx, "Client", Patched)
    data, body, signature = fetch_org_config("http://org/config")
    assert data["org"]["org_id"] == "x"
    assert verify_signature(body, signature, "sek")
