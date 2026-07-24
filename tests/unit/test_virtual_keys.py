"""F2 virtual keys: store, middleware, CLI (issue #111)."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from typer.testing import CliRunner

from daari.auth.virtual_keys import VirtualKeyStore
from daari.cli.app import app as cli_app
from daari.gateway.internal import DaariMeta, InternalRequest, InternalResponse, RequestMeta
from daari.router.router import AppContext
from daari.server.app import create_app
from daari.server.auth import apply_auth_claims_to_meta, resolve_auth
from daari.server.auth import AuthClaims


CHAT = {"model": "daari", "messages": [{"role": "user", "content": "hi"}]}


def _mock_execute(app):
    async def fake(request: InternalRequest) -> InternalResponse:
        return InternalResponse(
            content=f"ok:{request.meta.client_id}:{request.meta.tier_cap}",
            model="llama3.2:3b",
            daari_meta=DaariMeta(
                tier=request.meta.tier_cap or "L3",
                executor="ollama",
                provider_id="ollama",
                latency_ms=1,
            ),
        )

    app.state.ctx.router.ollama.execute = fake


class TestStore:
    def test_create_resolve_revoke(self, tmp_path):
        store = VirtualKeyStore(tmp_path / "keys.sqlite3")
        created = store.create("ci", rpm=10, tier_cap="L3", client_id="ci-bot")
        assert created.plaintext.startswith("dk_")
        found = store.resolve(created.plaintext)
        assert found is not None
        assert found.key_id == created.key.key_id
        assert found.tier_cap == "L3"
        assert store.revoke(created.key.key_id)
        assert store.resolve(created.plaintext) is None

    def test_rpm_limit(self, tmp_path):
        store = VirtualKeyStore(tmp_path / "keys.sqlite3")
        created = store.create("limited", rpm=2)
        key = store.resolve(created.plaintext)
        assert store.check_rpm(key)
        assert store.check_rpm(key)
        assert not store.check_rpm(key)


class TestResolveAuth:
    def test_master_key(self, tmp_path):
        store = VirtualKeyStore(tmp_path / "k.sqlite3")
        claims = resolve_auth("sekret", master_key="sekret", store=store)
        assert claims and claims.kind == "master"

    def test_virtual_key(self, tmp_path):
        store = VirtualKeyStore(tmp_path / "k.sqlite3")
        created = store.create("bot", client_id="bot")
        claims = resolve_auth(created.plaintext, master_key="sekret", store=store)
        assert claims and claims.kind == "virtual"
        assert claims.client_id == "bot"

    def test_apply_claims_defaults(self):
        meta = RequestMeta()
        apply_auth_claims_to_meta(
            meta,
            AuthClaims(kind="virtual", client_id="c1", tier_cap="L4"),
        )
        assert meta.client_id == "c1" and meta.tier_cap == "L4"
        meta2 = RequestMeta(client_id="header", tier_cap="L5")
        apply_auth_claims_to_meta(
            meta2, AuthClaims(kind="virtual", client_id="c1", tier_cap="L4")
        )
        assert meta2.client_id == "header" and meta2.tier_cap == "L5"


@pytest.mark.asyncio
async def test_virtual_key_accepted_alongside_master(settings, tmp_path):
    settings.server.api_key = "master"
    settings.server.virtual_keys.path = str(tmp_path / "vk.sqlite3")
    store = VirtualKeyStore(settings.virtual_keys_path)
    created = store.create("agent", client_id="agent", tier_cap="L3")
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    app.state.virtual_key_store = store
    app.state.ctx.virtual_key_store = store
    _mock_execute(app)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        bad = await client.post("/v1/chat/completions", json=CHAT)
        assert bad.status_code == 401
        master = await client.post(
            "/v1/chat/completions",
            json=CHAT,
            headers={"Authorization": "Bearer master"},
        )
        assert master.status_code == 200
        vk = await client.post(
            "/v1/chat/completions",
            json={"model": "daari", "messages": [{"role": "user", "content": "vk prompt"}]},
            headers={
                "Authorization": f"Bearer {created.plaintext}",
                "X-Daari-No-Cache": "true",
            },
        )
    assert vk.status_code == 200
    assert "ok:agent:L3" in vk.text


@pytest.mark.asyncio
async def test_rpm_returns_429(settings, tmp_path):
    settings.server.api_key = "master"
    settings.server.virtual_keys.path = str(tmp_path / "vk.sqlite3")
    store = VirtualKeyStore(settings.virtual_keys_path)
    created = store.create("burst", rpm=1)
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    app.state.virtual_key_store = store
    _mock_execute(app)
    transport = ASGITransport(app=app)
    headers = {"Authorization": f"Bearer {created.plaintext}"}
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        first = await client.post("/v1/chat/completions", json=CHAT, headers=headers)
        second = await client.post("/v1/chat/completions", json=CHAT, headers=headers)
    assert first.status_code == 200
    assert second.status_code == 429


class TestCLI:
    def test_create_list_revoke(self, tmp_path, monkeypatch):
        from daari.config.settings import Settings

        settings = Settings()
        settings.server.virtual_keys.path = str(tmp_path / "vk.sqlite3")
        monkeypatch.setattr("daari.cli.app.get_settings", lambda: settings)
        runner = CliRunner()
        created = runner.invoke(
            cli_app, ["keys", "create", "demo", "--rpm", "5", "--tier-cap", "L3"]
        )
        assert created.exit_code == 0
        assert "dk_" in created.output
        listed = runner.invoke(cli_app, ["keys", "list"])
        assert listed.exit_code == 0 and "demo" in listed.output
        key_id = [
            line.split()[0]
            for line in listed.output.splitlines()
            if line and not line.startswith("key_id")
        ][0]
        revoked = runner.invoke(cli_app, ["keys", "revoke", key_id])
        assert revoked.exit_code == 0
