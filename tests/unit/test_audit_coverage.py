"""Audit coverage for key lifecycle, failed auth, tenancy denials (#464)."""

from __future__ import annotations

import json

import pytest
from httpx import ASGITransport, AsyncClient
from typer.testing import CliRunner

from daari.auth.virtual_keys import VirtualKeyStore
from daari.cli.app import app as cli_app
from daari.enterprise.audit import (
    AuditLog,
    record_invalid_key,
    _invalid_key_seen,
)
from daari.gateway.internal import DaariMeta, InternalRequest, InternalResponse
from daari.router.router import AppContext
from daari.server.app import create_app


CHAT = {"model": "daari", "messages": [{"role": "user", "content": "hi"}]}


def _clear_invalid_key_dedupe() -> None:
    _invalid_key_seen.clear()


class TestKeyLifecycleAudit:
    def test_create_and_revoke_audit(self, tmp_path, monkeypatch):
        from daari.config.settings import Settings

        settings = Settings()
        settings.server.virtual_keys.path = str(tmp_path / "vk.sqlite3")
        settings.enterprise.audit_path = str(tmp_path / "audit.sqlite3")
        monkeypatch.setattr("daari.cli.app.get_settings", lambda: settings)
        runner = CliRunner()
        created = runner.invoke(cli_app, ["keys", "create", "demo"])
        assert created.exit_code == 0
        key_id = [
            line.split(":", 1)[1].strip()
            for line in created.output.splitlines()
            if line.startswith("key_id:")
        ][0]
        log = AuditLog(settings.enterprise.audit_path)
        creates = log.list(action="keys.create")
        assert len(creates) == 1
        detail = creates[0]["detail"]
        assert detail["key_id"] == key_id
        assert detail.get("prefix")
        assert created.output.splitlines()[-1] not in str(detail)  # no plaintext secret
        assert len(detail["prefix"]) <= 10

        revoked = runner.invoke(cli_app, ["keys", "revoke", key_id])
        assert revoked.exit_code == 0
        revokes = log.list(action="keys.revoke")
        assert len(revokes) == 1
        assert revokes[0]["detail"]["key_id"] == key_id
        assert log.verify().ok is True

    def test_team_create_and_update_audit(self, tmp_path, monkeypatch):
        from daari.config.settings import Settings

        settings = Settings()
        settings.server.virtual_keys.path = str(tmp_path / "vk.sqlite3")
        settings.enterprise.audit_path = str(tmp_path / "audit.sqlite3")
        monkeypatch.setattr("daari.cli.app.get_settings", lambda: settings)
        runner = CliRunner()
        created = runner.invoke(
            cli_app, ["keys", "team-create", "eng", "--daily-budget", "10"]
        )
        assert created.exit_code == 0, created.output
        team_id = [
            line.split(":", 1)[1].strip()
            for line in created.output.splitlines()
            if line.startswith("team_id:")
        ][0]
        log = AuditLog(settings.enterprise.audit_path)
        creates = log.list(action="teams.create")
        assert len(creates) == 1
        assert creates[0]["detail"]["team_id"] == team_id
        assert creates[0]["detail"]["name"] == "eng"

        # Idempotent create by name must not double-audit.
        again = runner.invoke(cli_app, ["keys", "team-create", "eng"])
        assert again.exit_code == 0
        assert len(log.list(action="teams.create")) == 1

        updated = runner.invoke(
            cli_app, ["keys", "team-update", team_id, "--monthly-budget", "50"]
        )
        assert updated.exit_code == 0, updated.output
        updates = log.list(action="teams.update")
        assert len(updates) == 1
        assert updates[0]["detail"]["team_id"] == team_id
        assert log.verify().ok is True


class TestInvalidKeyAudit:
    def test_flood_safe_dedupe(self, tmp_path):
        _clear_invalid_key_dedupe()
        audit = AuditLog(tmp_path / "audit.sqlite3")
        # Same first-10 prefix → one row; different path → separate bucket.
        assert record_invalid_key(audit, supplied="dk_abcdef0AAAA", path="/v1/chat")
        assert not record_invalid_key(audit, supplied="dk_abcdef0BBBB", path="/v1/chat")
        assert not record_invalid_key(audit, supplied="dk_abcdef0CCCC", path="/v1/chat")
        assert record_invalid_key(audit, supplied="dk_abcdef0AAAA", path="/v1/models")
        rows = audit.list(action="auth.invalid_key")
        assert len(rows) == 2
        assert rows[0]["detail"]["prefix"] == "dk_abcdef0"
        assert "AAAA" not in str(rows)

    @pytest.mark.asyncio
    async def test_gateway_records_invalid_key(self, settings, tmp_path, monkeypatch):
        _clear_invalid_key_dedupe()
        settings.server.api_key = "master-secret"
        settings.server.virtual_keys.path = str(tmp_path / "vk.sqlite3")
        settings.enterprise.audit_path = str(tmp_path / "audit.sqlite3")
        app = create_app(settings)
        app.state.ctx = AppContext.from_settings(settings)

        async def fake(request: InternalRequest) -> InternalResponse:
            return InternalResponse(
                content="ok",
                model="llama3.2:3b",
                daari_meta=DaariMeta(tier="L3", executor="ollama", latency_ms=1),
            )

        app.state.ctx.router.ollama.execute = fake
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            for _ in range(5):
                response = await client.post(
                    "/v1/chat/completions",
                    json=CHAT,
                    headers={"Authorization": "Bearer dk_badsecret999"},
                )
                assert response.status_code == 401
        rows = AuditLog(settings.enterprise.audit_path).list(action="auth.invalid_key")
        assert len(rows) == 1
        assert rows[0]["detail"]["prefix"] == "dk_badsecr"
        assert rows[0]["detail"]["path"] == "/v1/chat/completions"
        assert "dk_badsecret999" not in str(rows[0])


@pytest.mark.asyncio
async def test_tenancy_denied_audits_file_access(settings, tmp_path):
    settings.server.api_key = ""
    settings.server.virtual_keys.enabled = True
    settings.server.virtual_keys.path = str(tmp_path / "vk.sqlite3")
    settings.files.enabled = True
    settings.files.path = str(tmp_path / "files")
    settings.enterprise.audit_path = str(tmp_path / "audit.sqlite3")
    store = VirtualKeyStore(settings.virtual_keys_path)
    owner = store.create("owner")
    stranger = store.create("stranger")

    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    app.state.virtual_key_store = store

    async def fake(request: InternalRequest) -> InternalResponse:
        return InternalResponse(
            content="ok",
            model="m",
            daari_meta=DaariMeta(tier="L3", executor="ollama", latency_ms=1),
        )

    app.state.ctx.router.ollama.execute = fake

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        upload = await client.post(
            "/v1/files",
            headers={"Authorization": f"Bearer {owner.plaintext}"},
            files={"file": ("batch.jsonl", b'{"custom_id":"1"}\n', "application/jsonl")},
            data={"purpose": "batch"},
        )
        assert upload.status_code == 200, upload.text
        file_id = upload.json()["id"]
        denied = await client.get(
            f"/v1/files/{file_id}",
            headers={"Authorization": f"Bearer {stranger.plaintext}"},
        )
        assert denied.status_code == 404

    rows = AuditLog(settings.enterprise.audit_path).list(action="tenancy.denied")
    assert len(rows) == 1
    assert rows[0]["detail"]["kind"] == "file"
    assert rows[0]["detail"]["id"] == file_id
    assert rows[0]["detail"]["key_id"] == stranger.key.key_id
    assert AuditLog(settings.enterprise.audit_path).verify().ok is True
