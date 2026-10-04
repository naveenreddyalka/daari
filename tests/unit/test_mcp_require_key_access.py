"""Opt-in fail-closed when virtual key has no MCP grant (#1352, #1389)."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from daari.auth.virtual_keys import VirtualKey, VirtualKeyStore
from daari.config.settings import Settings
from daari.gateway.mcp_policy import (
    DENY_ALL_TOOLS,
    TOOL_DENIED,
    key_has_mcp_grant,
    resolve_policy,
    virtual_key_lacks_mcp_grant,
)
from daari.observability.prometheus import render_prometheus
from daari.router.router import AppContext
from daari.server.app import create_app
from daari.server.auth import AuthClaims

_INIT_PARAMS = {
    "protocolVersion": "2025-03-26",
    "capabilities": {},
    "clientInfo": {"name": "test", "version": "0"},
}


def _key(metadata=None) -> VirtualKey:
    return VirtualKey(
        key_id="k1",
        name="agent",
        prefix="dk_abc",
        metadata=metadata or {},
    )


def _claims(metadata=None, *, kind: str = "virtual") -> AuthClaims:
    if kind == "master":
        return AuthClaims(kind="master")
    key = _key(metadata)
    return AuthClaims(kind="virtual", key_id=key.key_id, client_id="agent", virtual_key=key)


class TestKeyHasMcpGrant:
    def test_missing_mcp_block_is_not_a_grant(self):
        assert key_has_mcp_grant({}) is False
        assert key_has_mcp_grant({"other": 1}) is False
        assert key_has_mcp_grant({"mcp": {}}) is False
        assert key_has_mcp_grant({"mcp": "nope"}) is False

    def test_allow_deny_or_servers_count(self):
        assert key_has_mcp_grant({"mcp": {"allow": ["route"]}}) is True
        assert key_has_mcp_grant({"mcp": {"deny": ["stats"]}}) is True
        assert key_has_mcp_grant({"mcp": {"allow": []}}) is True
        assert key_has_mcp_grant({"mcp": {"servers": {"allow": ["weather"]}}}) is True
        assert key_has_mcp_grant({"mcp": {"servers": {"deny": ["shell"]}}}) is True

    def test_clients_alone_is_not_a_tool_grant(self):
        assert key_has_mcp_grant({"mcp": {"clients": {"allow": ["claude-*"]}}}) is False
        assert key_has_mcp_grant({"mcp": {"servers": {}}}) is False


class TestRequireKeyAccessDefined:
    def test_flag_defaults_off(self):
        settings = Settings()
        assert settings.integrations.mcp_policy.require_key_access_defined is False

    def test_flag_off_never_lacks_grant(self):
        settings = Settings()
        assert virtual_key_lacks_mcp_grant(_claims({}), settings) is False

    def test_flag_on_vk_without_grant(self):
        settings = Settings.model_validate(
            {"integrations": {"mcp_policy": {"require_key_access_defined": True}}}
        )
        assert virtual_key_lacks_mcp_grant(_claims({}), settings) is True
        assert virtual_key_lacks_mcp_grant(_claims({"mcp": {}}), settings) is True

    def test_flag_on_vk_with_grant_ok(self):
        settings = Settings.model_validate(
            {"integrations": {"mcp_policy": {"require_key_access_defined": True}}}
        )
        assert (
            virtual_key_lacks_mcp_grant(_claims({"mcp": {"allow": ["route"]}}), settings)
            is False
        )
        assert (
            virtual_key_lacks_mcp_grant(
                _claims({"mcp": {"servers": {"allow": ["weather"]}}}), settings
            )
            is False
        )

    def test_master_and_anonymous_unchanged(self):
        settings = Settings.model_validate(
            {"integrations": {"mcp_policy": {"require_key_access_defined": True}}}
        )
        assert virtual_key_lacks_mcp_grant(_claims(kind="master"), settings) is False
        assert virtual_key_lacks_mcp_grant(None, settings) is False

    def test_resolve_policy_returns_deny_all_when_lacking_grant(self):
        settings = Settings.model_validate(
            {"integrations": {"mcp_policy": {"require_key_access_defined": True}}}
        )
        policy = resolve_policy(_claims({}), settings)
        assert policy == DENY_ALL_TOOLS
        assert not policy.allows("route")
        assert not policy.allows("stats")

    def test_resolve_policy_normal_when_granted(self):
        settings = Settings.model_validate(
            {
                "integrations": {
                    "mcp_policy": {
                        "require_key_access_defined": True,
                    }
                }
            }
        )
        policy = resolve_policy(_claims({"mcp": {"allow": ["route"]}}), settings)
        assert policy.allows("route")
        assert not policy.allows("stats")


def _vk_app(settings, *, metadata=None):
    store = VirtualKeyStore(settings.virtual_keys_path)
    created = store.create("agent", client_id="agent", metadata=metadata)
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    app.state.virtual_key_store = store
    app.state.ctx.virtual_key_store = store
    return app, {"Authorization": f"Bearer {created.plaintext}"}


async def _initialize(client, headers):
    return await client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": _INIT_PARAMS},
        headers=headers,
    )


@pytest.mark.asyncio
async def test_initialize_denied_when_vk_lacks_grant(settings):
    settings.integrations.mcp_policy.require_key_access_defined = True
    app, headers = _vk_app(settings)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await _initialize(client, headers)
    assert response.status_code == 403
    error = response.json()["error"]
    assert error["code"] == TOOL_DENIED
    assert "initialize" in error["message"].lower() or "grant" in error["message"].lower()


@pytest.mark.asyncio
async def test_initialize_ok_when_vk_has_grant(settings):
    settings.integrations.mcp_policy.require_key_access_defined = True
    app, headers = _vk_app(settings, metadata={"mcp": {"allow": ["route"]}})
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await _initialize(client, headers)
    assert response.status_code == 200
    result = response.json()["result"]
    assert "tools" in result["capabilities"]


@pytest.mark.asyncio
async def test_initialize_ok_when_flag_off(settings):
    assert settings.integrations.mcp_policy.require_key_access_defined is False
    app, headers = _vk_app(settings)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await _initialize(client, headers)
    assert response.status_code == 200
    assert "result" in response.json()


def _grant_denied_count(app) -> int:
    metrics = app.state.ctx.metrics
    snap = metrics.snapshot(include_histograms=True)
    return int(snap.get("mcp_grant_denied") or 0)


@pytest.mark.asyncio
async def test_stats_json_exposes_mcp_grant_denied(settings):
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        before = await client.get("/v1/daari/stats")
        assert before.status_code == 200
        assert before.json().get("mcp_grant_denied", 0) == 0
        app.state.ctx.metrics.record_mcp_grant_denied()
        after = await client.get("/v1/daari/stats")
    assert after.json()["mcp_grant_denied"] == 1
    settings.integrations.mcp_policy.require_key_access_defined = True
    app, headers = _vk_app(settings)
    assert _grant_denied_count(app) == 0
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        denied = await _initialize(client, headers)
    assert denied.status_code == 403
    assert _grant_denied_count(app) == 1
    assert "daari_mcp_grant_denied_total 1" in render_prometheus(app.state.ctx.metrics)


@pytest.mark.asyncio
async def test_tools_list_fail_closed_increments_mcp_grant_denied(settings):
    settings.integrations.mcp_policy.require_key_access_defined = True
    app, headers = _vk_app(settings)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        listed = await client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
            headers=headers,
        )
    assert listed.json()["result"]["tools"] == []
    assert _grant_denied_count(app) == 1


@pytest.mark.asyncio
async def test_ordinary_tool_deny_does_not_increment_mcp_grant_denied(settings, monkeypatch):
    from daari.gateway.internal import DaariMeta, InternalRequest, InternalResponse
    from tests.conftest import mock_all_ollama_executors

    app, headers = _vk_app(settings, metadata={"mcp": {"deny": ["stats"]}})

    async def fake_execute(_request: InternalRequest) -> InternalResponse:
        return InternalResponse(
            content="ok",
            model="llama3.2:3b",
            daari_meta=DaariMeta(tier="L3", executor="ollama", provider_id="ollama:l3"),
        )

    mock_all_ollama_executors(monkeypatch, app.state.ctx.router, fake_execute)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        denied = await client.post(
            "/mcp",
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": "stats", "arguments": {}},
            },
            headers=headers,
        )
    assert denied.json()["error"]["code"] == TOOL_DENIED
    assert _grant_denied_count(app) == 0


@pytest.mark.asyncio
async def test_granted_initialize_does_not_increment_mcp_grant_denied(settings):
    settings.integrations.mcp_policy.require_key_access_defined = True
    app, headers = _vk_app(settings, metadata={"mcp": {"allow": ["route"]}})
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        ok = await _initialize(client, headers)
    assert ok.status_code == 200
    assert _grant_denied_count(app) == 0


@pytest.mark.asyncio
async def test_mcp_grant_denied_noop_when_prometheus_disabled(settings):
    settings.observability.prometheus = False
    settings.integrations.mcp_policy.require_key_access_defined = True
    app, headers = _vk_app(settings)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        denied = await _initialize(client, headers)
    assert denied.status_code == 403
    assert _grant_denied_count(app) == 0
