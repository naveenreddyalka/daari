"""Master-key gate for config editor writes when SSO is off (#1441)."""

from __future__ import annotations

from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from daari.auth.virtual_keys import VirtualKeyStore
from daari.enterprise.sso import mint_dev_token
from daari.router.router import AppContext
from daari.server.app import create_app
from daari.setup.doctor import _check_config_editor_ungoverned, run_doctor

ROOT = Path(__file__).resolve().parents[2]
HTTP_API = ROOT / "docs/developer/reference/http-api.md"
WEB_UI_README = ROOT / "packages/web-ui/README.md"
AUTH_KEYS = ROOT / "docs/developer/guides/configuration/auth-and-keys.md"
DOCTOR_HEALTH = ROOT / "docs/developer/guides/operations/doctor-health.md"


@pytest.mark.asyncio
async def test_vk_forbidden_on_patch_when_master_set_sso_off(settings, tmp_path):
    settings.observability.config_editor = True
    settings.server.api_key = "master-sekret"
    settings.server.virtual_keys.path = str(tmp_path / "vk.sqlite3")
    settings.enterprise.sso.enabled = False
    store = VirtualKeyStore(settings.virtual_keys_path)
    created = store.create("agent", client_id="agent", daily_budget_usd=1.0)
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    app.state.virtual_key_store = store
    app.state.ctx.virtual_key_store = store
    transport = ASGITransport(app=app)
    headers_vk = {"Authorization": f"Bearer {created.plaintext}"}
    headers_master = {"Authorization": "Bearer master-sekret"}
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # GET stays viewer-style for virtual keys.
        got = await client.get("/v1/daari/config", headers=headers_vk)
        assert got.status_code == 200

        denied = await client.patch(
            "/v1/daari/config",
            headers=headers_vk,
            json={"routing": {"prefer": "latency"}},
        )
        assert denied.status_code == 403

        persist_denied = await client.patch(
            "/v1/daari/config",
            headers=headers_vk,
            json={"routing": {"prefer": "balanced"}, "persist": True},
        )
        assert persist_denied.status_code == 403

        ok = await client.patch(
            "/v1/daari/config",
            headers=headers_master,
            json={"routing": {"prefer": "latency"}},
        )
        assert ok.status_code == 200
        assert ok.json()["routing"]["prefer"] == "latency"


@pytest.mark.asyncio
async def test_open_sandbox_without_master_still_allows_patch(settings):
    settings.observability.config_editor = True
    settings.server.api_key = ""
    settings.server.dangerously_permit_weak_or_unset_api_key = True
    settings.enterprise.sso.enabled = False
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        patched = await client.patch(
            "/v1/daari/config",
            json={"routing": {"prefer": "cost"}},
        )
        assert patched.status_code == 200


@pytest.mark.asyncio
async def test_sso_on_admin_path_unchanged(settings, tmp_path):
    settings.observability.config_editor = True
    settings.server.api_key = "master-sekret"
    settings.enterprise.sso.enabled = True
    settings.enterprise.sso.secret = "sso-hs-secret"
    settings.enterprise.sso.issuer = "daari-dev"
    settings.enterprise.audit_path = str(tmp_path / "audit.sqlite3")

    token = mint_dev_token(
        subject="alice", role="admin", secret="sso-hs-secret", issuer="daari-dev"
    )
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        ok = await client.patch(
            "/v1/daari/config",
            headers={"Authorization": f"Bearer {token}"},
            json={"routing": {"prefer": "balanced"}},
        )
        assert ok.status_code == 200


def test_doctor_warns_ungoverned_config_editor_without_master(settings):
    settings.observability.config_editor = True
    settings.server.api_key = ""
    settings.server.dangerously_permit_weak_or_unset_api_key = True
    settings.enterprise.sso.enabled = False
    row = _check_config_editor_ungoverned(settings)
    assert row is not None
    assert row.name == "config_editor_ungoverned"
    assert row.optional is True
    assert row.ok is False
    assert "ungoverned" in row.detail.lower() or "master key" in row.detail.lower()


def test_doctor_quiet_when_master_set_or_editor_off(settings):
    settings.observability.config_editor = True
    settings.server.api_key = "master-sekret"
    settings.enterprise.sso.enabled = False
    assert _check_config_editor_ungoverned(settings) is None

    settings.observability.config_editor = False
    settings.server.api_key = ""
    assert _check_config_editor_ungoverned(settings) is None
    rows = run_doctor(settings, httpx_client=None)
    assert not any(r.name == "config_editor_ungoverned" for r in rows)


def test_docs_pin_master_key_config_ownership():
    http_api = HTTP_API.read_text(encoding="utf-8")
    assert "master key" in http_api.lower()
    assert "virtual key" in http_api.lower() or "virtual keys" in http_api.lower()
    section = http_api.split("## Config editor ownership", 1)[1].split("## ", 1)[0]
    assert "PATCH" in section
    assert "GET" in section

    readme = WEB_UI_README.read_text(encoding="utf-8")
    assert "master key" in readme.lower()
    assert "save" in readme.lower()

    auth = AUTH_KEYS.read_text(encoding="utf-8")
    assert "master key" in auth.lower()
    assert "SSO off" in auth or "sso is off" in auth.lower() or "SSO is off" in auth

    doctor = DOCTOR_HEALTH.read_text(encoding="utf-8")
    assert "config_editor_ungoverned" in doctor
