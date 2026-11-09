"""Offboarding kill switch: revoke every key for an SSO subject (#2145)."""

from __future__ import annotations

import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from typer.testing import CliRunner

from daari.auth.postgres_virtual_keys import PostgresVirtualKeyStore
from daari.auth.virtual_keys import VirtualKeyStore
from daari.cli.app import app as cli_app
from daari.enterprise.audit import AuditLog
from daari.enterprise.sso_keys import revoke_subject_keys
from daari.gateway.internal import DaariMeta, InternalRequest, InternalResponse
from daari.router.router import AppContext
from daari.server.app import create_app


def _dsn() -> str:
    return f"memory:revoke-subject-{uuid.uuid4().hex}"


def test_revoke_subject_keys_sqlite_selective(tmp_path):
    store = VirtualKeyStore(tmp_path / "vk.sqlite3")
    team = store.create_team("eng")
    alice_keys = [
        store.create(f"alice-{i}", client_id="sso:alice") for i in range(3)
    ]
    bob = store.create("bob", client_id="sso:bob")
    store.set_team_memberships("alice", [team.team_id])
    store.set_team_memberships("sso:alice", [team.team_id])
    store.set_team_memberships("sso:bob", [team.team_id])

    audit = AuditLog(tmp_path / "audit.sqlite3")
    result = revoke_subject_keys(
        store,
        subject="alice",
        audit=audit,
        actor="ops",
        role="admin",
    )
    assert result["revoked"] == 3
    assert {k.key.key_id for k in alice_keys} == set(result["key_ids"])
    assert all(store.resolve(k.plaintext) is None for k in alice_keys)
    assert store.resolve(bob.plaintext) is not None
    assert store.list_team_memberships("alice") == []
    assert store.list_team_memberships("sso:alice") == []
    assert store.list_team_memberships("sso:bob") == [team.team_id]
    events = [e for e in audit.list() if e["action"] == "keys.revoke_subject"]
    assert len(events) == 3
    assert all(e["detail"]["subject"] == "alice" for e in events)

    again = revoke_subject_keys(
        store,
        subject="alice",
        audit=audit,
        actor="ops",
        role="admin",
    )
    assert again["revoked"] == 0


def test_revoke_subject_matches_bare_and_sso_client_id(tmp_path):
    store = VirtualKeyStore(tmp_path / "vk.sqlite3")
    bare = store.create("bare", client_id="alice")
    prefixed = store.create("prefixed", client_id="sso:alice")
    other = store.create("other", client_id="alice-other")
    audit = AuditLog(tmp_path / "audit.sqlite3")
    result = revoke_subject_keys(
        store, subject="alice", audit=audit, actor="cli", role="admin"
    )
    assert result["revoked"] == 2
    assert store.resolve(bare.plaintext) is None
    assert store.resolve(prefixed.plaintext) is None
    assert store.resolve(other.plaintext) is not None


def test_revoke_subject_keys_postgres(tmp_path):
    store = PostgresVirtualKeyStore(_dsn())
    a1 = store.create("a1", client_id="sso:alice")
    a2 = store.create("a2", client_id="alice")
    bob = store.create("bob", client_id="sso:bob")
    audit = AuditLog(tmp_path / "audit.sqlite3")
    result = revoke_subject_keys(
        store, subject="alice", audit=audit, actor="ops", role="admin"
    )
    assert result["revoked"] == 2
    assert store.resolve(a1.plaintext) is None
    assert store.resolve(a2.plaintext) is None
    assert store.resolve(bob.plaintext) is not None


def test_revoke_subject_rotated_key_stays_revoked(tmp_path):
    store = VirtualKeyStore(tmp_path / "vk.sqlite3")
    created = store.create("alice", client_id="sso:alice")
    rotated = store.rotate(created.key.key_id, grace="1h")
    audit = AuditLog(tmp_path / "audit.sqlite3")
    result = revoke_subject_keys(
        store, subject="alice", audit=audit, actor="ops", role="admin"
    )
    assert result["revoked"] == 1
    assert result["key_ids"] == [created.key.key_id]
    assert store.resolve(rotated.plaintext) is None
    assert store.resolve(created.plaintext) is None


def test_cli_revoke_subject(tmp_path, monkeypatch):
    from daari.config.settings import Settings

    settings = Settings()
    settings.server.virtual_keys.path = str(tmp_path / "vk.sqlite3")
    settings.enterprise.audit_path = str(tmp_path / "audit.sqlite3")
    monkeypatch.setattr("daari.cli.app.get_settings", lambda: settings)
    store = VirtualKeyStore(settings.virtual_keys_path)
    for i in range(3):
        store.create(f"a{i}", client_id="sso:alice")
    store.create("bob", client_id="sso:bob")
    runner = CliRunner()
    result = runner.invoke(cli_app, ["keys", "revoke-subject", "alice"])
    assert result.exit_code == 0, result.output
    assert "3" in result.output
    again = runner.invoke(cli_app, ["keys", "revoke-subject", "alice"])
    assert again.exit_code == 0, again.output
    assert "0" in again.output


def _mock_execute(app):
    async def fake(request: InternalRequest) -> InternalResponse:
        return InternalResponse(
            content="ok",
            model="llama3.2:3b",
            daari_meta=DaariMeta(tier="L3", executor="ollama", latency_ms=1),
        )

    app.state.ctx.router.ollama.execute = fake


@pytest.mark.asyncio
async def test_http_revoke_subject_requires_admin_and_returns_count(settings, tmp_path):
    settings.server.api_key = "master-sekret"
    settings.server.virtual_keys.path = str(tmp_path / "vk.sqlite3")
    settings.enterprise.sso.enabled = False
    settings.enterprise.audit_path = str(tmp_path / "audit.sqlite3")
    store = VirtualKeyStore(settings.virtual_keys_path)
    keys = [store.create(f"a{i}", client_id="sso:alice") for i in range(3)]
    bob = store.create("bob", client_id="sso:bob")
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    app.state.virtual_key_store = store
    app.state.ctx.virtual_key_store = store
    _mock_execute(app)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        denied = await client.post(
            "/v1/daari/keys/revoke-subject",
            headers={"Authorization": f"Bearer {bob.plaintext}"},
            json={"subject": "alice"},
        )
        assert denied.status_code == 403

        ok = await client.post(
            "/v1/daari/keys/revoke-subject",
            headers={"Authorization": "Bearer master-sekret"},
            json={"subject": "alice"},
        )
        assert ok.status_code == 200
        assert ok.json() == {"revoked": 3}

        for created in keys:
            assert store.resolve(created.plaintext) is None
        assert store.resolve(bob.plaintext) is not None

        chat = await client.post(
            "/v1/chat/completions",
            headers={"Authorization": f"Bearer {keys[0].plaintext}"},
            json={"model": "llama3.2:3b", "messages": [{"role": "user", "content": "hi"}]},
        )
        assert chat.status_code in (401, 403)

        idempotent = await client.post(
            "/v1/daari/keys/revoke-subject",
            headers={"Authorization": "Bearer master-sekret"},
            json={"subject": "alice"},
        )
        assert idempotent.status_code == 200
        assert idempotent.json() == {"revoked": 0}
