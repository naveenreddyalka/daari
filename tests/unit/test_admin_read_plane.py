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
        assert ok.json() == {"keys": []}

        teams = await client.get(
            "/v1/daari/teams",
            headers={"Authorization": "Bearer master-sekret"},
        )
        assert teams.status_code == 200
        assert teams.json() == {"teams": []}
