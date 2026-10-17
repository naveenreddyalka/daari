"""Audit events list and team filters on keys, teams, and audit (#1711)."""

from __future__ import annotations

import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from daari.auth.virtual_keys import VirtualKeyStore
from daari.enterprise.postgres_audit import audit_log_from_settings
from daari.enterprise.sso import mint_dev_token
from daari.gateway import request_log
from daari.gateway.postgres_request_log import PostgresRequestLogStore
from daari.gateway.request_log import configure_request_log
from daari.router.router import AppContext
from daari.server.app import create_app


@pytest.fixture(autouse=True)
def _reset_request_log():
    yield
    configure_request_log(
        path=request_log.DEFAULT_LOG_PATH,
        max_bytes=request_log.DEFAULT_MAX_BYTES,
        backups=request_log.DEFAULT_BACKUPS,
        structured_json_logs=False,
        otlp_logs=False,
        backend="jsonl",
        postgres_url="",
    )


def _app(settings, tmp_path):
    settings.server.api_key = "master-sekret"
    settings.server.virtual_keys.path = str(tmp_path / "vk.sqlite3")
    if not settings.enterprise.sso.secret:
        settings.enterprise.sso.enabled = False
    settings.enterprise.audit_path = str(tmp_path / "audit.sqlite3")
    store = VirtualKeyStore(settings.virtual_keys_path)
    team_a = store.create_team("alpha")
    team_b = store.create_team("beta")
    store.create("alice", team=team_a.name, client_id="alice")
    store.create("bob", team=team_b.name, client_id="bob")
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    app.state.virtual_key_store = store
    app.state.ctx.virtual_key_store = store
    return app, store, team_a, team_b


@pytest.mark.asyncio
async def test_events_list_writes_audit_row_without_bodies(settings, tmp_path):
    dsn = f"memory:events-audit-{uuid.uuid4().hex}"
    settings.observability.request_log.backend = "postgres"
    settings.observability.postgres_url = dsn
    app, _store, team_a, _team_b = _app(settings, tmp_path)
    log = PostgresRequestLogStore(dsn)
    log.append("chat", {"team_id": team_a.team_id, "prompt": "secret-body"})
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(
            "/v1/daari/events",
            params={"limit": 10, "team_id": team_a.team_id},
            headers={
                "Authorization": "Bearer master-sekret",
                "X-Daari-Actor": "ops",
            },
        )
    assert resp.status_code == 200
    assert resp.json()["events"]
    audit = audit_log_from_settings(settings)
    rows = [row for row in audit.list(limit=20) if row["action"] == "admin.events.list"]
    assert len(rows) == 1
    row = rows[0]
    assert row["actor"] == "ops"
    assert row["role"] == "admin"
    detail = row["detail"]
    assert detail["limit"] == 10
    assert detail["team_id"] == team_a.team_id
    assert detail["returned"] == 1
    assert "secret-body" not in str(detail)
    assert "events" not in detail


@pytest.mark.asyncio
async def test_keys_and_teams_filter_by_team_and_cross_team_403(settings, tmp_path):
    settings.enterprise.sso.enabled = True
    settings.enterprise.sso.secret = "sso-hs-secret"
    settings.enterprise.sso.issuer = "daari-dev"
    app, _store, team_a, team_b = _app(settings, tmp_path)
    master = {"Authorization": "Bearer master-sekret"}
    scoped = {
        "Authorization": "Bearer "
        + mint_dev_token(
            subject="lead",
            role="admin",
            secret="sso-hs-secret",
            issuer="daari-dev",
            extra={"team_id": team_a.team_id},
        )
    }
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        full = await client.get("/v1/daari/keys", headers=master)
        assert full.status_code == 200
        assert full.json()["total"] == 2

        only = await client.get(
            "/v1/daari/keys",
            params={"team_id": team_b.team_id},
            headers=master,
        )
        assert only.status_code == 200
        body = only.json()
        assert body["total"] == 1
        assert body["keys"][0]["team_id"] == team_b.team_id

        teams = await client.get(
            "/v1/daari/teams",
            params={"team_id": team_a.team_id},
            headers=master,
        )
        assert teams.status_code == 200
        assert teams.json()["total"] == 1
        assert teams.json()["teams"][0]["team_id"] == team_a.team_id

        denied = await client.get(
            "/v1/daari/keys",
            params={"team_id": team_b.team_id},
            headers=scoped,
        )
        assert denied.status_code == 403
        denied_teams = await client.get(
            "/v1/daari/teams",
            params={"team_id": team_b.team_id},
            headers=scoped,
        )
        assert denied_teams.status_code == 403


@pytest.mark.asyncio
async def test_audit_team_filter_pagination(settings, tmp_path):
    app, _store, team_a, team_b = _app(settings, tmp_path)
    audit = audit_log_from_settings(settings)
    audit.record(actor="a", role="admin", action="note", detail={"team_id": team_a.team_id, "n": 1})
    audit.record(actor="a", role="admin", action="note", detail={"n": 2})
    audit.record(actor="a", role="admin", action="note", detail={"team_id": team_b.team_id, "n": 3})
    audit.record(actor="a", role="admin", action="note", detail={"team_id": team_a.team_id, "n": 4})
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        page = await client.get(
            "/v1/daari/audit",
            params={"team_id": team_a.team_id, "limit": 1, "offset": 0},
            headers={"Authorization": "Bearer master-sekret"},
        )
        assert page.status_code == 200
        body = page.json()
        assert body["total"] == 2
        assert body["has_more"] is True
        assert len(body["entries"]) == 1
        assert body["entries"][0]["detail"]["team_id"] == team_a.team_id

        page2 = await client.get(
            "/v1/daari/audit",
            params={"team_id": team_a.team_id, "limit": 1, "offset": 1},
            headers={"Authorization": "Bearer master-sekret"},
        )
        assert page2.status_code == 200
        body2 = page2.json()
        assert body2["total"] == 2
        assert body2["has_more"] is False
        assert body2["entries"][0]["detail"]["team_id"] == team_a.team_id
        assert body2["entries"][0]["detail"]["n"] != body["entries"][0]["detail"]["n"]
