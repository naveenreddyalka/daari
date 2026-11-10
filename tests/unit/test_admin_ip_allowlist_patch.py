"""Admin PATCH for per-key / per-team allowed_ips (#2154)."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from daari.auth.virtual_keys import VirtualKeyStore
from daari.enterprise.postgres_audit import audit_log_from_settings
from daari.router.router import AppContext
from daari.server.app import create_app


def _app_with_store(settings, tmp_path, *, master: str = "master-sekret"):
    settings.server.api_key = master
    settings.server.virtual_keys.path = str(tmp_path / "vk.sqlite3")
    settings.enterprise.sso.enabled = False
    settings.enterprise.audit_path = str(tmp_path / "audit.sqlite3")
    store = VirtualKeyStore(settings.virtual_keys_path)
    team = store.create_team("eng")
    created = store.create("alice", team="eng", allowed_ips=["10.0.0.0/8"])
    vk = store.create("viewer")
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    app.state.virtual_key_store = store
    app.state.ctx.virtual_key_store = store
    return app, store, created, team, vk


@pytest.mark.asyncio
async def test_patch_key_allowed_ips_set_clear_and_reject(settings, tmp_path):
    app, store, created, _team, vk = _app_with_store(settings, tmp_path)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        denied = await client.patch(
            f"/v1/daari/keys/{created.key.key_id}",
            headers={"Authorization": f"Bearer {vk.plaintext}"},
            json={"allowed_ips": ["203.0.113.0/24"]},
        )
        assert denied.status_code == 403

        bad = await client.patch(
            f"/v1/daari/keys/{created.key.key_id}",
            headers={"Authorization": "Bearer master-sekret"},
            json={"allowed_ips": ["not-an-ip"]},
        )
        assert bad.status_code == 400
        assert "invalid" in str(bad.json().get("detail", "")).lower()

        ok = await client.patch(
            f"/v1/daari/keys/{created.key.key_id}",
            headers={
                "Authorization": "Bearer master-sekret",
                "x-daari-actor": "ops-bob",
            },
            json={"allowed_ips": ["203.0.113.10", "2001:db8::/64"]},
        )
        assert ok.status_code == 200
        body = ok.json()
        assert body["key_id"] == created.key.key_id
        assert body["allowed_ips"] == ["203.0.113.10/32", "2001:db8::/64"]

        found = store.resolve(created.plaintext)
        assert found is not None
        assert found.allowed_ips == ("203.0.113.10/32", "2001:db8::/64")

        cleared = await client.patch(
            f"/v1/daari/keys/{created.key.key_id}",
            headers={"Authorization": "Bearer master-sekret"},
            json={"allowed_ips": []},
        )
        assert cleared.status_code == 200
        assert cleared.json()["allowed_ips"] is None
        assert store.resolve(created.plaintext).allowed_ips is None

        missing = await client.patch(
            "/v1/daari/keys/does-not-exist",
            headers={"Authorization": "Bearer master-sekret"},
            json={"allowed_ips": ["10.0.0.0/8"]},
        )
        assert missing.status_code == 404

    rows = audit_log_from_settings(settings).list(action="admin.keys.patch_ips")
    assert len(rows) >= 1
    assert any(row.get("actor") == "ops-bob" for row in rows)


@pytest.mark.asyncio
async def test_patch_team_allowed_ips_set_clear_and_reject(settings, tmp_path):
    app, store, _created, team, vk = _app_with_store(settings, tmp_path)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        denied = await client.patch(
            f"/v1/daari/teams/{team.team_id}",
            headers={"Authorization": f"Bearer {vk.plaintext}"},
            json={"allowed_ips": ["203.0.113.0/24"]},
        )
        assert denied.status_code == 403

        bad = await client.patch(
            f"/v1/daari/teams/{team.team_id}",
            headers={"Authorization": "Bearer master-sekret"},
            json={"allowed_ips": ["999.999.999.999"]},
        )
        assert bad.status_code == 400

        ok = await client.patch(
            f"/v1/daari/teams/{team.team_id}",
            headers={"Authorization": "Bearer master-sekret"},
            json={"allowed_ips": ["198.51.100.0/24"]},
        )
        assert ok.status_code == 200
        assert ok.json()["allowed_ips"] == ["198.51.100.0/24"]
        assert store.get_team(team.team_id).allowed_ips == ("198.51.100.0/24",)

        cleared = await client.patch(
            f"/v1/daari/teams/{team.team_id}",
            headers={"Authorization": "Bearer master-sekret"},
            json={"allowed_ips": None},
        )
        assert cleared.status_code == 200
        assert cleared.json()["allowed_ips"] is None
        assert store.get_team(team.team_id).allowed_ips is None
