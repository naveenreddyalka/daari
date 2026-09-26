"""Request-time team selection with membership enforcement (#1107)."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from typer.testing import CliRunner

from daari.auth.virtual_keys import VirtualKeyStore
from daari.cli.app import app as cli_app
from daari.gateway.internal import RequestMeta
from daari.router.router import AppContext
from daari.server.auth import (
    apply_auth_claims_to_meta,
    apply_selected_team,
    resolve_auth,
    resolve_team_header,
)
from daari.server.app import create_app


CHAT = {
    "model": "daari",
    "messages": [{"role": "user", "content": "hi"}],
}


def test_membership_round_trip(tmp_path):
    store = VirtualKeyStore(tmp_path / "keys.sqlite3")
    platform = store.create_team("platform")
    research = store.create_team("research")
    store.set_team_memberships("alice", [platform.team_id, research.team_id])
    assert store.is_team_member("alice", platform.team_id)
    assert store.is_team_member("alice", research.team_id)
    assert store.list_team_memberships("alice") == sorted(
        [platform.team_id, research.team_id]
    )
    store.set_team_memberships("alice", [platform.team_id])
    assert not store.is_team_member("alice", research.team_id)


def test_header_override_requires_membership_and_flag(tmp_path):
    store = VirtualKeyStore(tmp_path / "keys.sqlite3")
    store.create_team("platform")
    research = store.create_team("research")
    created = store.create(
        "dev",
        client_id="alice",
        team="platform",
        metadata={"allow_team_override": True},
    )
    store.add_team_membership("alice", research.team_id)
    claims = resolve_auth(created.plaintext, master_key="master", store=store)
    assert claims is not None
    selected, err = resolve_team_header(
        {"x-daari-team": research.name}, claims, store
    )
    assert err is None
    assert selected == research.team_id
    apply_selected_team(claims, selected, store)
    meta = RequestMeta()
    apply_auth_claims_to_meta(meta, claims)
    assert meta.team_id == research.team_id

    other = store.create("other", client_id="bob", metadata={"allow_team_override": True})
    selected, err = resolve_team_header(
        {"x-daari-team": "platform"},
        resolve_auth(other.plaintext, master_key="master", store=store),
        store,
    )
    assert selected is None
    assert err is not None
    assert err["code"] == "team_membership_required"


def test_pinned_team_blocks_override_without_flag(tmp_path):
    store = VirtualKeyStore(tmp_path / "keys.sqlite3")
    store.create_team("platform")
    research = store.create_team("research")
    created = store.create("dev", client_id="alice", team="platform")
    store.add_team_membership("alice", research.team_id)
    claims = resolve_auth(created.plaintext, master_key="master", store=store)
    _, err = resolve_team_header({"x-daari-team": "research"}, claims, store)
    assert err is not None
    assert err["code"] == "team_override_denied"


def test_cli_team_members(tmp_path, monkeypatch, settings):
    path = tmp_path / "keys.sqlite3"
    settings.server.virtual_keys.path = str(path)
    settings.server.virtual_keys.enabled = True
    monkeypatch.setattr("daari.cli.app.get_settings", lambda: settings)
    store = VirtualKeyStore(path)
    team = store.create_team("platform")
    result = CliRunner().invoke(
        cli_app,
        ["keys", "team-members", "alice", "--team", "platform"],
    )
    assert result.exit_code == 0, result.stdout + result.stderr
    assert store.is_team_member("alice", team.team_id)


@pytest.mark.asyncio
async def test_gateway_team_header_member_and_forbidden(settings, tmp_path, monkeypatch):
    settings.server.api_key = "master"
    settings.server.virtual_keys.path = str(tmp_path / "vk.sqlite3")
    settings.server.virtual_keys.enabled = True
    store = VirtualKeyStore(settings.virtual_keys_path)
    platform = store.create_team("platform")
    research = store.create_team("research")
    created = store.create(
        "dev",
        client_id="alice",
        team="platform",
        metadata={"allow_team_override": True},
    )
    store.add_team_membership("alice", research.team_id)
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    app.state.virtual_key_store = store
    app.state.ctx.virtual_key_store = store

    async def fake_execute(request):
        from daari.gateway.internal import DaariMeta, InternalResponse

        return InternalResponse(
            content=f"ok:{request.meta.team_id}",
            model="llama3.2:3b",
            daari_meta=DaariMeta(
                tier="L3",
                executor="ollama",
                provider_id="ollama",
                model="llama3.2:3b",
                latency_ms=1,
            ),
        )

    from tests.conftest import mock_all_ollama_executors

    mock_all_ollama_executors(monkeypatch, app.state.ctx.router, fake_execute)
    transport = ASGITransport(app=app)
    headers = {
        "Authorization": f"Bearer {created.plaintext}",
        "X-Daari-No-Cache": "true",
        "X-Daari-Team": "research",
    }
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        denied = await client.post(
            "/v1/chat/completions",
            json=CHAT,
            headers={
                "Authorization": f"Bearer {created.plaintext}",
                "X-Daari-Team": "unknown-team",
            },
        )
        assert denied.status_code == 403
        assert denied.json()["error"]["code"] == "team_not_found"

        ok = await client.post("/v1/chat/completions", json=CHAT, headers=headers)
        assert ok.status_code == 200
        assert research.team_id in ok.text

        default = await client.post(
            "/v1/chat/completions",
            json=CHAT,
            headers={
                "Authorization": f"Bearer {created.plaintext}",
                "X-Daari-No-Cache": "true",
            },
        )
        assert default.status_code == 200
        assert platform.team_id in default.text

    claims = resolve_auth(created.plaintext, master_key="master", store=store)
    selected, err = resolve_team_header({"x-daari-team": "research"}, claims, store)
    assert err is None
    apply_selected_team(claims, selected, store)
    meta = RequestMeta()
    apply_auth_claims_to_meta(meta, claims)
    assert meta.team_id == research.team_id
    assert meta.team_id != platform.team_id
