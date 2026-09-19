"""RFC 7662 POST /introspect for virtual keys (#618)."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from daari.auth.virtual_keys import VirtualKeyStore
from daari.router.router import AppContext
from daari.server.app import create_app
from daari.server.auth import introspect_token


@pytest.fixture
def settings(tmp_path):
    from daari.config.settings import Settings

    return Settings.model_validate(
        {
            "server": {
                "host": "127.0.0.1",
                "port": 11435,
                "api_key": "master-secret",
                "virtual_keys": {"path": str(tmp_path / "vk.sqlite3"), "enabled": True},
            },
            "models": {"l3": "llama3.2:3b"},
            "ollama": {"base_url": "http://127.0.0.1:11434"},
            "cache": {"l0": {"enabled": True, "path": str(tmp_path / "l0")}},
        }
    )


def test_introspect_token_master():
    payload = introspect_token("master-secret", master_key="master-secret", store=None)
    assert payload["active"] is True
    assert payload["username"] == "master"


def test_introspect_token_unknown():
    payload = introspect_token("nope", master_key="master-secret", store=None)
    assert payload == {"active": False}


def test_introspect_token_virtual_key(tmp_path):
    store = VirtualKeyStore(tmp_path / "vk.sqlite3")
    store.create_team("eng", rpm=10, tpm=1000)
    created = store.create(
        "alice",
        client_id="cid-a",
        team="eng",
        tier_cap="L3",
        rpm=5,
        tpm=500,
        expires_at="2099-01-01T00:00:00+00:00",
    )
    payload = introspect_token(created.plaintext, master_key="master-secret", store=store)
    assert payload["active"] is True
    assert payload["client_id"] == "cid-a"
    assert payload["username"] == "alice"
    assert payload["team_id"]
    assert payload["team_name"] == "eng"
    assert payload["tier_cap"] == "L3"
    assert payload["rpm"] == 5
    assert payload["tpm"] == 500
    assert "rpd" not in payload
    assert "exp" in payload
    assert "plaintext" not in payload
    assert created.plaintext not in str(payload)


def test_introspect_includes_rpd_when_set(tmp_path):
    store = VirtualKeyStore(tmp_path / "vk.sqlite3")
    created = store.create("alice", rpm=5, rpd=9)
    payload = introspect_token(created.plaintext, master_key="master-secret", store=store)
    assert payload["active"] is True
    assert payload["rpm"] == 5
    assert payload["rpd"] == 9


def test_introspect_token_revoked_inactive(tmp_path):
    store = VirtualKeyStore(tmp_path / "vk.sqlite3")
    created = store.create("bob", client_id="cid-b")
    store.revoke(created.key.key_id)
    payload = introspect_token(created.plaintext, master_key="master-secret", store=store)
    assert payload == {"active": False}


@pytest.mark.asyncio
async def test_introspect_endpoint_json_and_form(settings, tmp_path):
    store = VirtualKeyStore(settings.virtual_keys_path)
    created = store.create("alice", client_id="cid-a", tier_cap="L4")
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    app.state.virtual_key_store = store
    app.state.ctx.virtual_key_store = store

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        denied = await client.post("/introspect", json={"token": created.plaintext})
        assert denied.status_code == 401

        ok_json = await client.post(
            "/introspect",
            json={"token": created.plaintext},
            headers={"Authorization": "Bearer master-secret"},
        )
        assert ok_json.status_code == 200
        body = ok_json.json()
        assert body["active"] is True
        assert body["username"] == "alice"
        assert body["tier_cap"] == "L4"

        ok_form = await client.post(
            "/introspect",
            data={"token": created.plaintext},
            headers={"Authorization": "Bearer master-secret"},
        )
        assert ok_form.status_code == 200
        assert ok_form.json()["active"] is True

        inactive = await client.post(
            "/introspect",
            json={"token": "dk_unknown"},
            headers={"Authorization": "Bearer master-secret"},
        )
        assert inactive.status_code == 200
        assert inactive.json() == {"active": False}

        # Virtual key may call introspect on another token.
        other = store.create("other", client_id="cid-o")
        via_vk = await client.post(
            "/introspect",
            json={"token": other.plaintext},
            headers={"Authorization": f"Bearer {created.plaintext}"},
        )
        assert via_vk.status_code == 200
        assert via_vk.json()["active"] is True
        assert via_vk.json()["username"] == "other"
