"""Hot-reload Settings from config.yaml without a process restart (#1234)."""

from __future__ import annotations

import asyncio
import signal
from pathlib import Path

import pytest
import yaml
from httpx import ASGITransport, AsyncClient
from typer.testing import CliRunner

from daari.auth.virtual_keys import VirtualKeyStore
from daari.config.settings import Settings
from daari.router.router import AppContext
from daari.server import config_reload
from daari.server.app import create_app
from daari.server.config_reload import (
    ConfigReloadError,
    diff_settings,
    install_sighup_reload,
    reload_config,
    reload_settings_from_disk,
)

ROOT = Path(__file__).resolve().parents[2]
HTTP_API = ROOT / "docs/developer/reference/http-api.md"
CONFIG_OVERVIEW = ROOT / "docs/developer/guides/configuration/overview.md"
TRACKING = ROOT / "docs/TRACKING.md"


def _write_config(home: Path, document: dict | str) -> Path:
    path = home / ".daari" / "config.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    text = document if isinstance(document, str) else yaml.safe_dump(document)
    path.write_text(text, encoding="utf-8")
    return path


def _app(settings):
    application = create_app(settings)
    application.state.ctx = AppContext.from_settings(settings)
    return application


@pytest.mark.asyncio
async def test_reload_applies_safe_keys_and_lists_requires_restart(
    settings, tmp_path, monkeypatch
):
    monkeypatch.setenv("HOME", str(tmp_path))
    settings.observability.config_editor = True
    settings.server.dangerously_permit_weak_or_unset_api_key = True
    assert settings.routing.prefer != "cost"
    _write_config(
        tmp_path,
        {
            "routing": {"prefer": "cost", "confidence_threshold": 0.42},
            "server": {"port": 19999},
        },
    )
    app = _app(settings)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        reloaded = await client.post("/v1/daari/reload-config")
        assert reloaded.status_code == 200, reloaded.text
        payload = reloaded.json()
        assert payload["ok"] is True
        assert "routing.prefer" in payload["changed_keys"]
        assert "routing.confidence_threshold" in payload["changed_keys"]
        assert "server.port" in payload["requires_restart"]
        assert "server.port" not in payload["changed_keys"]
        assert payload["path"].endswith("config.yaml")

        observed = await client.get("/v1/daari/config")
    assert observed.status_code == 200
    body = observed.json()
    assert body["routing"]["prefer"] == "cost"
    assert body["routing"]["confidence_threshold"] == pytest.approx(0.42)
    assert body["ownership"]["routing.prefer"]["source"] == "file"
    assert app.state.ctx.router.model_preference == "cost"
    assert app.state.ctx.router.confidence_threshold == pytest.approx(0.42)
    # Unsafe keys are reported, never swapped live.
    assert app.state.ctx.settings.server.port != 19999


@pytest.mark.asyncio
async def test_invalid_yaml_returns_400_and_keeps_prior_settings(
    settings, tmp_path, monkeypatch
):
    monkeypatch.setenv("HOME", str(tmp_path))
    settings.server.dangerously_permit_weak_or_unset_api_key = True
    before = settings.routing.prefer
    _write_config(tmp_path, "routing: [unclosed\n  prefer: cost\n")
    app = _app(settings)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/v1/daari/reload-config")
    assert response.status_code == 400
    assert "reload" in response.json()["detail"].lower()
    assert app.state.ctx.settings.routing.prefer == before
    assert app.state.ctx.router.model_preference == before


@pytest.mark.asyncio
async def test_invalid_value_returns_400_and_keeps_prior_settings(
    settings, tmp_path, monkeypatch
):
    monkeypatch.setenv("HOME", str(tmp_path))
    settings.server.dangerously_permit_weak_or_unset_api_key = True
    before = settings.routing.confidence_threshold
    _write_config(tmp_path, {"routing": {"confidence_threshold": 7.5}})
    app = _app(settings)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/v1/daari/reload-config")
    assert response.status_code == 400
    assert app.state.ctx.settings.routing.confidence_threshold == before


@pytest.mark.asyncio
async def test_reload_requires_master_key_when_sso_off(settings, tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    settings.server.api_key = "master-sekret"
    settings.server.virtual_keys.path = str(tmp_path / "vk.sqlite3")
    settings.enterprise.sso.enabled = False
    store = VirtualKeyStore(settings.virtual_keys_path)
    created = store.create("agent", client_id="agent", daily_budget_usd=1.0)
    _write_config(tmp_path, {"routing": {"prefer": "cost"}})
    app = _app(settings)
    app.state.virtual_key_store = store
    app.state.ctx.virtual_key_store = store
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        anonymous = await client.post("/v1/daari/reload-config")
        assert anonymous.status_code == 401
        denied = await client.post(
            "/v1/daari/reload-config",
            headers={"Authorization": f"Bearer {created.plaintext}"},
        )
        assert denied.status_code == 403
        assert app.state.ctx.settings.routing.prefer != "cost"
        ok = await client.post(
            "/v1/daari/reload-config",
            headers={"Authorization": "Bearer master-sekret"},
        )
        assert ok.status_code == 200, ok.text
        assert app.state.ctx.settings.routing.prefer == "cost"


@pytest.mark.asyncio
async def test_reload_clears_runtime_overrides_and_file_wins(
    settings, tmp_path, monkeypatch
):
    monkeypatch.setenv("HOME", str(tmp_path))
    settings.observability.config_editor = True
    settings.server.dangerously_permit_weak_or_unset_api_key = True
    _write_config(tmp_path, {"routing": {"prefer": "cost"}})
    app = _app(settings)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        patched = await client.patch(
            "/v1/daari/config", json={"routing": {"prefer": "latency"}}
        )
        assert patched.status_code == 200
        assert patched.json()["ownership"]["routing.prefer"]["source"] == "runtime"
        assert "routing.prefer" in app.state.config_runtime_overrides

        reloaded = await client.post("/v1/daari/reload-config")
        assert reloaded.status_code == 200
        assert "routing.prefer" in reloaded.json()["changed_keys"]

        observed = await client.get("/v1/daari/config")
    assert observed.json()["routing"]["prefer"] == "cost"
    assert observed.json()["ownership"]["routing.prefer"]["source"] == "file"
    assert not app.state.config_runtime_overrides


@pytest.mark.asyncio
async def test_reload_without_changes_is_noop(settings, tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    settings.server.dangerously_permit_weak_or_unset_api_key = True
    app = _app(settings)
    app.state.settings_loader = lambda: settings.model_copy(deep=True)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/v1/daari/reload-config")
    assert response.status_code == 200
    assert response.json()["changed_keys"] == []
    assert response.json()["requires_restart"] == []


@pytest.mark.asyncio
async def test_reload_records_audit_event(settings, tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    settings.server.dangerously_permit_weak_or_unset_api_key = True
    settings.enterprise.audit_path = str(tmp_path / "audit.sqlite3")
    _write_config(tmp_path, {"routing": {"prefer": "cost"}})
    app = _app(settings)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/v1/daari/reload-config", headers={"x-daari-actor": "ops"}
        )
        assert response.status_code == 200
    from daari.enterprise.postgres_audit import audit_log_from_settings

    rows = audit_log_from_settings(app.state.ctx.settings).list(20, action="config.reload")
    assert rows
    assert rows[0]["actor"] == "ops"
    assert "routing.prefer" in rows[0]["detail"]["changed_keys"]
    assert rows[0]["detail"]["trigger"] == "api"


def test_diff_settings_classifies_safe_and_restart_keys(settings):
    fresh = settings.model_copy(deep=True)
    fresh.routing.prefer = "cost"
    fresh.cache.l0.ttl_seconds = settings.cache.l0.ttl_seconds + 5
    fresh.server.port = settings.server.port + 1
    fresh.frontier.enabled = not settings.frontier.enabled
    diff = diff_settings(settings, fresh)
    assert diff.changed_keys == ["cache.l0_ttl_seconds", "routing.prefer"]
    assert diff.requires_restart == ["frontier.enabled", "server.port"]
    assert diff.patch["routing"] == {"prefer": "cost"}
    assert diff.patch["cache"] == {"l0_ttl_seconds": settings.cache.l0.ttl_seconds + 5}


def test_diff_settings_mcp_server_ceilings_are_live_but_url_needs_restart():
    base = Settings.model_validate(
        {
            "integrations": {
                "mcp_servers": [
                    {"id": "docs", "url": "http://a.example/mcp", "rpm": 10, "tpm": 100},
                ]
            }
        }
    )
    ceilings_only = base.model_copy(deep=True)
    ceilings_only.integrations.mcp_servers[0].rpm = 20
    diff = diff_settings(base, ceilings_only)
    assert diff.changed_keys == ["integrations.mcp_servers"]
    assert diff.requires_restart == []
    assert diff.patch["integrations"]["mcp_servers"] == [{"id": "docs", "rpm": 20, "tpm": 100}]

    url_change = base.model_copy(deep=True)
    url_change.integrations.mcp_servers[0].url = "http://b.example/mcp"
    diff = diff_settings(base, url_change)
    assert diff.changed_keys == []
    assert diff.requires_restart == ["integrations.mcp_servers"]

    added = base.model_copy(deep=True)
    added.integrations.mcp_servers.append(
        type(base.integrations.mcp_servers[0]).model_validate(
            {"id": "new", "url": "http://c.example/mcp"}
        )
    )
    diff = diff_settings(base, added)
    assert "integrations.mcp_servers" in diff.requires_restart
    assert "integrations" not in diff.patch


def test_diff_settings_skills_prefix_is_live():
    base = Settings.model_validate({})
    fresh = base.model_copy(deep=True)
    fresh.skills_system_prefix = "# skill\nbe terse"
    diff = diff_settings(base, fresh)
    assert diff.changed_keys == ["skills_system_prefix"]
    assert diff.requires_restart == []


def test_reload_settings_from_disk_uses_app_loader_and_applies_skills_prefix(settings):
    settings.server.dangerously_permit_weak_or_unset_api_key = True
    app = _app(settings)
    fresh = settings.model_copy(deep=True)
    fresh.skills_system_prefix = "# skill\nbe terse"
    expected_budget = settings.routing.latency_budget_ms + 100
    fresh.routing.latency_budget_ms = expected_budget
    app.state.settings_loader = lambda: fresh
    payload = reload_settings_from_disk(app, trigger="test")
    assert payload["ok"] is True
    assert payload["trigger"] == "test"
    assert payload["changed_keys"] == ["routing.latency_budget_ms", "skills_system_prefix"]
    assert app.state.ctx.settings.skills_system_prefix == "# skill\nbe terse"
    assert app.state.ctx.router.skills_system_prefix == "# skill\nbe terse"
    assert app.state.ctx.router.latency_budget_ms == expected_budget
    assert app.state.ctx.settings.routing.latency_budget_ms == expected_budget


def test_reload_settings_from_disk_loader_failure_raises_and_keeps_settings(settings):
    settings.server.dangerously_permit_weak_or_unset_api_key = True
    app = _app(settings)
    before = settings.routing.prefer

    def boom() -> Settings:
        raise RuntimeError("secret://vault/missing failed")

    app.state.settings_loader = boom
    with pytest.raises(ConfigReloadError, match="reload"):
        reload_settings_from_disk(app)
    assert app.state.ctx.settings.routing.prefer == before


@pytest.mark.asyncio
async def test_reload_config_serializes_concurrent_calls(settings):
    settings.server.dangerously_permit_weak_or_unset_api_key = True
    app = _app(settings)
    app.state.settings_loader = lambda: settings.model_copy(deep=True)
    results = await asyncio.gather(
        reload_config(app, trigger="a"), reload_config(app, trigger="b")
    )
    assert [row["ok"] for row in results] == [True, True]
    assert isinstance(app.state.config_reload_lock, asyncio.Lock)


class _FakeLoop:
    def __init__(self, *, fail: Exception | None = None) -> None:
        self.handlers: dict[int, object] = {}
        self.removed: list[int] = []
        self.tasks: list[object] = []
        self._fail = fail

    def add_signal_handler(self, sig, callback, *args):
        if self._fail is not None:
            raise self._fail
        self.handlers[sig] = callback

    def remove_signal_handler(self, sig):
        self.removed.append(sig)
        return self.handlers.pop(sig, None) is not None

    def create_task(self, coro):
        self.tasks.append(coro)
        coro.close()
        return coro


def test_install_sighup_reload_registers_and_removes(settings, monkeypatch):
    settings.server.dangerously_permit_weak_or_unset_api_key = True
    app = _app(settings)
    loop = _FakeLoop()
    remove = install_sighup_reload(app, loop=loop)
    assert callable(remove)
    assert signal.SIGHUP in loop.handlers
    loop.handlers[signal.SIGHUP]()
    assert len(loop.tasks) == 1
    remove()
    assert loop.removed == [signal.SIGHUP]


def test_install_sighup_reload_skips_without_sighup_or_when_disabled(settings, monkeypatch):
    settings.server.dangerously_permit_weak_or_unset_api_key = True
    app = _app(settings)
    monkeypatch.setattr(config_reload, "_SIGHUP", None)
    assert install_sighup_reload(app, loop=_FakeLoop()) is None
    monkeypatch.setattr(config_reload, "_SIGHUP", signal.SIGHUP)
    settings.server.sighup_reload = False
    assert install_sighup_reload(app, loop=_FakeLoop()) is None


def test_install_sighup_reload_tolerates_non_main_thread(settings):
    settings.server.dangerously_permit_weak_or_unset_api_key = True
    app = _app(settings)
    loop = _FakeLoop(fail=ValueError("signal only works in main thread"))
    assert install_sighup_reload(app, loop=loop) is None


def test_serve_registers_settings_loader_that_reapplies_cli_flags(monkeypatch):
    from daari.cli.app import app as cli_app

    captured: dict = {}

    def fake_load(*, strict: bool = False):
        return Settings.model_validate(
            {"server": {"dangerously_permit_weak_or_unset_api_key": True}}
        )

    class _State:
        pass

    class _App:
        state = _State()

    def fake_create_app(settings):
        captured["settings"] = settings
        return _App()

    def fake_run(_app, **kwargs):
        captured["app"] = _app

    monkeypatch.setattr("daari.cli.app.Settings.load", fake_load)
    monkeypatch.setattr("daari.cli.app.create_app", fake_create_app)
    monkeypatch.setattr("daari.cli.app.uvicorn.run", fake_run)
    result = CliRunner().invoke(cli_app, ["serve", "--no-frontier"])
    assert result.exit_code == 0, result.output
    loader = captured["app"].state.settings_loader
    assert callable(loader)
    fresh = loader()
    assert fresh is not captured["settings"]
    assert fresh.frontier.enabled is False


def test_docs_mention_reload_config():
    http_api = HTTP_API.read_text(encoding="utf-8")
    assert "/v1/daari/reload-config" in http_api
    assert "requires_restart" in http_api
    assert "SIGHUP" in http_api
    overview = CONFIG_OVERVIEW.read_text(encoding="utf-8")
    assert "reload-config" in overview
    assert "SIGHUP" in overview
    tracking = TRACKING.read_text(encoding="utf-8")
    assert "<!-- tracking:#1234 -->" in tracking
