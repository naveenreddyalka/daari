"""Admin-gated read-only keys/teams inventories (#1477)."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from daari.auth.virtual_keys import BudgetWindow, VirtualKeyStore
from daari.enterprise.sso import mint_dev_token
from daari.router.router import AppContext
from daari.server.app import create_app

FORBIDDEN_FIELDS = frozenset(
    {
        "key_hash",
        "previous_key_hash",
        "plaintext",
        "secret",
        "token",
        "api_key",
        "hash",
    }
)


def _app_with_keys(settings, tmp_path, *, master: str = "master-sekret"):
    settings.server.api_key = master
    settings.server.virtual_keys.path = str(tmp_path / "vk.sqlite3")
    settings.enterprise.sso.enabled = False
    store = VirtualKeyStore(settings.virtual_keys_path)
    team = store.create_team(
        "eng",
        budget_windows=[BudgetWindow("day", 10.0)],
        rpm=60,
        tpm=10000,
        rpd=500,
    )
    created = store.create(
        "alice",
        client_id="alice",
        team=team.name,
        daily_budget_usd=1.0,
        monthly_budget_usd=20.0,
        tier_cap="L3",
        rpm=10,
        tpm=1000,
        rpd=50,
        expires_at="2099-01-01T00:00:00+00:00",
    )
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    app.state.virtual_key_store = store
    app.state.ctx.virtual_key_store = store
    return app, store, created, team


def _assert_no_secrets(payload: dict) -> None:
    for row in payload.get("keys") or payload.get("teams") or []:
        assert isinstance(row, dict)
        lowered = {str(k).lower() for k in row}
        for forbidden in FORBIDDEN_FIELDS:
            assert forbidden not in lowered
        assert "key_hash" not in row
        assert "previous_key_hash" not in row



@pytest.mark.asyncio
async def test_keys_requires_master_when_sso_off(settings, tmp_path):
    app, store, created, _team = _app_with_keys(settings, tmp_path)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        denied = await client.get(
            "/v1/daari/keys",
            headers={"Authorization": f"Bearer {created.plaintext}"},
        )
        assert denied.status_code == 403

        ok = await client.get(
            "/v1/daari/keys",
            headers={"Authorization": "Bearer master-sekret"},
        )
        assert ok.status_code == 200
        body = ok.json()
        assert "keys" in body
        assert len(body["keys"]) == 1
        row = body["keys"][0]
        assert row["key_id"] == created.key.key_id
        assert row["name"] == "alice"
        assert row["team_id"] == created.key.team_id
        assert row["tier_cap"] == "L3"
        assert row["expires_at"] == "2099-01-01T00:00:00+00:00"
        assert "budgets" in row or "budget_windows" in row or "daily_budget_usd" in row
        assert "spend" in row
        _assert_no_secrets(body)
        assert created.plaintext not in str(body)


@pytest.mark.asyncio
async def test_teams_requires_master_when_sso_off(settings, tmp_path):
    app, _store, created, team = _app_with_keys(settings, tmp_path)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        denied = await client.get(
            "/v1/daari/teams",
            headers={"Authorization": f"Bearer {created.plaintext}"},
        )
        assert denied.status_code == 403

        ok = await client.get(
            "/v1/daari/teams",
            headers={"Authorization": "Bearer master-sekret"},
        )
        assert ok.status_code == 200
        body = ok.json()
        assert "teams" in body
        assert len(body["teams"]) == 1
        row = body["teams"][0]
        assert row["team_id"] == team.team_id
        assert row["name"] == "eng"
        assert row["rpm"] == 60
        assert "spend" in row
        _assert_no_secrets(body)


@pytest.mark.asyncio
async def test_keys_sso_admin_role_allows(settings, tmp_path):
    settings.server.api_key = "master-sekret"
    settings.server.virtual_keys.path = str(tmp_path / "vk.sqlite3")
    settings.enterprise.sso.enabled = True
    settings.enterprise.sso.secret = "sso-hs-secret"
    settings.enterprise.sso.issuer = "daari-dev"
    store = VirtualKeyStore(settings.virtual_keys_path)
    store.create("bob", client_id="bob", daily_budget_usd=2.0)
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    app.state.virtual_key_store = store
    app.state.ctx.virtual_key_store = store
    token = mint_dev_token(
        subject="ops", role="admin", secret="sso-hs-secret", issuer="daari-dev"
    )
    viewer = mint_dev_token(
        subject="viewer", role="viewer", secret="sso-hs-secret", issuer="daari-dev"
    )
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        denied = await client.get(
            "/v1/daari/keys",
            headers={"Authorization": f"Bearer {viewer}"},
        )
        assert denied.status_code == 403

        ok = await client.get(
            "/v1/daari/keys",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert ok.status_code == 200
        assert len(ok.json()["keys"]) == 1


@pytest.mark.asyncio
async def test_keys_empty_when_store_missing(settings):
    settings.server.api_key = "master-sekret"
    settings.enterprise.sso.enabled = False
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        ok = await client.get(
            "/v1/daari/keys",
            headers={"Authorization": "Bearer master-sekret"},
        )
        assert ok.status_code == 200
        keys_body = ok.json()
        assert keys_body["keys"] == []
        assert keys_body["total"] == 0
        assert keys_body["has_more"] is False
        assert "limit" in keys_body
        assert keys_body["offset"] == 0

        teams = await client.get(
            "/v1/daari/teams",
            headers={"Authorization": "Bearer master-sekret"},
        )
        assert teams.status_code == 200
        teams_body = teams.json()
        assert teams_body["teams"] == []
        assert teams_body["total"] == 0
        assert teams_body["has_more"] is False
        assert "limit" in teams_body
        assert teams_body["offset"] == 0


@pytest.mark.asyncio
async def test_keys_pagination_truncates_large_store(settings, tmp_path):
    settings.server.api_key = "master-sekret"
    settings.server.virtual_keys.path = str(tmp_path / "vk.sqlite3")
    settings.enterprise.sso.enabled = False
    store = VirtualKeyStore(settings.virtual_keys_path)
    for i in range(5):
        store.create(f"user-{i}", client_id=f"user-{i}", daily_budget_usd=1.0)
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    app.state.virtual_key_store = store
    app.state.ctx.virtual_key_store = store
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        page = await client.get(
            "/v1/daari/keys",
            params={"limit": 2, "offset": 0},
            headers={"Authorization": "Bearer master-sekret"},
        )
        assert page.status_code == 200
        body = page.json()
        assert body["total"] == 5
        assert body["limit"] == 2
        assert body["offset"] == 0
        assert len(body["keys"]) == 2
        assert body["has_more"] is True
        _assert_no_secrets(body)

        page2 = await client.get(
            "/v1/daari/keys",
            params={"limit": 2, "offset": 4},
            headers={"Authorization": "Bearer master-sekret"},
        )
        assert page2.status_code == 200
        body2 = page2.json()
        assert body2["total"] == 5
        assert len(body2["keys"]) == 1
        assert body2["has_more"] is False
        _assert_no_secrets(body2)


@pytest.mark.asyncio
async def test_teams_pagination_truncates_large_store(settings, tmp_path):
    settings.server.api_key = "master-sekret"
    settings.server.virtual_keys.path = str(tmp_path / "vk.sqlite3")
    settings.enterprise.sso.enabled = False
    store = VirtualKeyStore(settings.virtual_keys_path)
    for i in range(4):
        store.create_team(f"team-{i}", rpm=10)
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    app.state.virtual_key_store = store
    app.state.ctx.virtual_key_store = store
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        page = await client.get(
            "/v1/daari/teams",
            params={"limit": 2, "offset": 1},
            headers={"Authorization": "Bearer master-sekret"},
        )
        assert page.status_code == 200
        body = page.json()
        assert body["total"] == 4
        assert body["limit"] == 2
        assert body["offset"] == 1
        assert len(body["teams"]) == 2
        assert body["has_more"] is True
        _assert_no_secrets(body)


@pytest.mark.asyncio
async def test_keys_list_emits_audit_entry(settings, tmp_path):
    from daari.enterprise.postgres_audit import audit_log_from_settings

    app, _store, _created, _team = _app_with_keys(settings, tmp_path)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        ok = await client.get(
            "/v1/daari/keys",
            params={"limit": 10, "offset": 0},
            headers={
                "Authorization": "Bearer master-sekret",
                "x-daari-actor": "ops-alice",
            },
        )
        assert ok.status_code == 200
    rows = audit_log_from_settings(settings).list(action="admin.keys.list")
    assert len(rows) >= 1
    row = rows[0]
    assert row["actor"] == "ops-alice"
    assert row["role"] == "admin"
    detail = row.get("detail") or {}
    if isinstance(detail, str):
        import json

        detail = json.loads(detail)
    assert detail.get("total") == 1
    assert detail.get("returned") == 1


@pytest.mark.asyncio
async def test_teams_list_emits_audit_entry(settings, tmp_path):
    from daari.enterprise.postgres_audit import audit_log_from_settings

    app, _store, _created, _team = _app_with_keys(settings, tmp_path)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        ok = await client.get(
            "/v1/daari/teams",
            headers={
                "Authorization": "Bearer master-sekret",
                "x-daari-actor": "ops-bob",
            },
        )
        assert ok.status_code == 200
    rows = audit_log_from_settings(settings).list(action="admin.teams.list")
    assert len(rows) >= 1
    row = rows[0]
    assert row["actor"] == "ops-bob"
    assert row["role"] == "admin"
