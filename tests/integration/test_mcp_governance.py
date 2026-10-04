"""MCP tool governance on the ingress: allow/deny policy, list filtering, audit (issue #277)."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from daari.auth.virtual_keys import VirtualKeyStore
from daari.enterprise.audit import AuditLog
from daari.gateway.internal import DaariMeta, InternalRequest, InternalResponse
from daari.gateway.mcp_policy import TOOL_DENIED
from daari.router.router import AppContext
from daari.server.app import create_app
from tests.conftest import mock_all_ollama_executors

pytestmark = pytest.mark.asyncio


def _app_with_key(settings, monkeypatch, *, metadata=None, team=None):
    store = VirtualKeyStore(settings.virtual_keys_path)
    created = store.create("agent", client_id="agent", team=team, metadata=metadata)
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    app.state.virtual_key_store = store
    app.state.ctx.virtual_key_store = store

    async def fake_execute(_request: InternalRequest) -> InternalResponse:
        return InternalResponse(
            content="routed",
            model="llama3.2:3b",
            daari_meta=DaariMeta(tier="L3", executor="ollama", provider_id="ollama:l3"),
        )

    mock_all_ollama_executors(monkeypatch, app.state.ctx.router, fake_execute)
    return app, {"Authorization": f"Bearer {created.plaintext}"}, created.key.key_id


async def _rpc(client, method, params=None, *, headers, rpc_id=1):
    body = {"jsonrpc": "2.0", "id": rpc_id, "method": method}
    if params is not None:
        body["params"] = params
    return await client.post("/mcp", json=body, headers=headers)


async def test_denied_tool_call_is_jsonrpc_error(settings, monkeypatch):
    app, headers, _ = _app_with_key(settings, monkeypatch, metadata={"mcp": {"deny": ["stats"]}})
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        denied = await _rpc(
            client, "tools/call", {"name": "stats", "arguments": {}}, headers=headers
        )
        allowed = await _rpc(
            client, "tools/call", {"name": "route", "arguments": {"input": "hi"}}, headers=headers
        )
    assert denied.status_code == 200
    error = denied.json()["error"]
    assert error["code"] == TOOL_DENIED
    assert "stats" in error["message"]
    assert error["data"]["tool"] == "stats"
    assert allowed.json()["result"]["content"][0]["text"] == "routed"


async def test_tools_list_filters_to_allowed_tools(settings, monkeypatch):
    app, headers, _ = _app_with_key(settings, monkeypatch, metadata={"mcp": {"allow": ["route"]}})
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        listed = await _rpc(client, "tools/list", headers=headers)
        legacy = await client.post("/v1/mcp/query", json={"tool": "tools/list"}, headers=headers)
    names = {tool["name"] for tool in listed.json()["result"]["tools"]}
    assert names == {"route"}
    legacy_names = {tool["name"] for tool in legacy.json()["result"]["tools"]}
    assert "stats" not in legacy_names
    assert "route" in legacy_names


async def test_every_tool_call_writes_an_audit_row_without_arguments(settings, monkeypatch):
    app, headers, key_id = _app_with_key(
        settings, monkeypatch, metadata={"mcp": {"deny": ["stats"]}}, team="eng"
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await _rpc(
            client,
            "tools/call",
            {"name": "route", "arguments": {"input": "very-secret-prompt"}},
            headers=headers,
        )
        await _rpc(client, "tools/call", {"name": "stats", "arguments": {}}, headers=headers)
    rows = [
        row
        for row in AuditLog(settings.enterprise.audit_path).list()
        if row["action"] == "mcp.tools/call"
    ]
    decisions = {(row["detail"]["tool"], row["detail"]["decision"]) for row in rows}
    assert decisions == {("route", "allow"), ("stats", "deny")}
    for row in rows:
        assert row["actor"] == key_id
        assert row["role"] == "eng"
        assert "arguments" not in row["detail"]
    assert "very-secret-prompt" not in str(rows)


async def test_legacy_rest_denied_tool_is_403(settings, monkeypatch):
    app, headers, _ = _app_with_key(settings, monkeypatch, metadata={"mcp": {"deny": ["stats"]}})
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        via_call = await client.post(
            "/v1/mcp/query",
            json={"tool": "tools/call", "args": {"name": "stats", "arguments": {}}},
            headers=headers,
        )
        direct = await client.post("/v1/mcp/query", json={"tool": "stats"}, headers=headers)
    for response in (via_call, direct):
        assert response.status_code == 403
        payload = response.json()
        assert payload["ok"] is False
        assert payload["result"]["error"]["code"] == "MCP_ERR_TOOL_DENIED"


async def test_global_policy_governs_master_key(settings, monkeypatch):
    settings.server.api_key = "sekret"
    settings.integrations.mcp_policy.deny = ["stats"]
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    headers = {"Authorization": "Bearer sekret"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        denied = await _rpc(
            client, "tools/call", {"name": "stats", "arguments": {}}, headers=headers
        )
        listed = await _rpc(client, "tools/list", headers=headers)
    assert denied.json()["error"]["code"] == TOOL_DENIED
    assert "stats" not in {tool["name"] for tool in listed.json()["result"]["tools"]}
    rows = AuditLog(settings.enterprise.audit_path).list()
    assert rows and rows[0]["actor"] == "master"


async def test_team_policy_applies_to_team_keys(settings, monkeypatch):
    settings.integrations.mcp_team_policies = {"eng": {"deny": ["stats"]}}
    app, headers, _ = _app_with_key(settings, monkeypatch, team="eng")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        denied = await _rpc(
            client, "tools/call", {"name": "stats", "arguments": {}}, headers=headers
        )
    assert denied.json()["error"]["code"] == TOOL_DENIED


async def test_mcp_name_header_is_honoured_for_policy(settings, monkeypatch):
    """Matching Mcp-Name still participates in policy; mismatches are 400 (#1233)."""
    app, headers, _ = _app_with_key(settings, monkeypatch, metadata={"mcp": {"deny": ["stats"]}})
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        denied = await _rpc(
            client,
            "tools/call",
            {"name": "stats", "arguments": {}},
            headers={**headers, "Mcp-Method": "tools/call", "Mcp-Name": "stats"},
        )
        mismatch = await _rpc(
            client,
            "tools/call",
            {"name": "route", "arguments": {"input": "hi"}},
            headers={**headers, "Mcp-Method": "tools/call", "Mcp-Name": "stats"},
        )
    assert denied.json()["error"]["code"] == TOOL_DENIED
    assert mismatch.status_code == 400
    assert mismatch.json()["error"]["code"] == -32023


async def test_server_policy_filters_catalog_and_denies_call(settings, monkeypatch):
    """Per-key mcp.servers allowlist hides denied egress tools (#1201)."""
    settings.integrations.mcp_servers = [
        {"id": "weather", "url": "http://mcp.test/weather"},
        {"id": "shell", "url": "http://mcp.test/shell"},
    ]
    app, headers, key_id = _app_with_key(
        settings,
        monkeypatch,
        metadata={"mcp": {"servers": {"allow": ["weather"]}}},
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        listed = await _rpc(client, "tools/list", headers=headers)
        denied = await _rpc(
            client,
            "tools/call",
            {"name": "mcp_shell", "arguments": {"input": "whoami"}},
            headers=headers,
        )

    names = {tool["name"] for tool in listed.json()["result"]["tools"]}
    assert "mcp_weather" in names
    assert "mcp_shell" not in names
    assert "route" in names
    error = denied.json()["error"]
    assert error["code"] == TOOL_DENIED
    assert error["data"]["tool"] == "mcp_shell"
    assert error["data"].get("server") == "shell"
    rows = [
        row
        for row in AuditLog(settings.enterprise.audit_path).list()
        if row["action"] == "mcp.tools/call" and row["detail"].get("decision") == "deny"
    ]
    assert len(rows) == 1
    assert rows[0]["detail"]["server"] == "shell"
    assert rows[0]["actor"] == key_id


async def test_client_allowlist_hit_and_deny_miss(settings, monkeypatch):
    """Per-key mcp.clients allow/deny gates initialize / tools/list (#1215)."""
    from daari.gateway.mcp_policy import CLIENT_DENIED

    app, headers, key_id = _app_with_key(
        settings,
        monkeypatch,
        metadata={"mcp": {"clients": {"allow": ["claude-code"], "deny": []}}},
    )
    meta_ok = {
        "_meta": {
            "io.modelcontextprotocol/clientInfo": {"name": "claude-code", "version": "0"},
        }
    }
    meta_bad = {
        "_meta": {
            "io.modelcontextprotocol/clientInfo": {"name": "evil-bot", "version": "0"},
        }
    }
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        allowed = await _rpc(client, "initialize", {**meta_ok, "protocolVersion": "2025-03-26", "capabilities": {}, "clientInfo": {"name": "claude-code", "version": "0"}}, headers=headers)
        denied = await _rpc(client, "tools/list", meta_bad, headers=headers)
        unset_passthrough_app, unset_headers, _ = _app_with_key(settings, monkeypatch)
    assert "result" in allowed.json()
    assert "error" not in allowed.json()
    error = denied.json()["error"]
    assert error["code"] == CLIENT_DENIED
    assert error["data"]["client"] == "evil-bot"
    rows = [
        row
        for row in AuditLog(settings.enterprise.audit_path).list()
        if row["action"] == "mcp.client" and row["detail"].get("decision") == "deny"
    ]
    assert len(rows) == 1
    assert rows[0]["actor"] == key_id
    assert rows[0]["detail"]["method"] == "tools/list"

    async with AsyncClient(
        transport=ASGITransport(app=unset_passthrough_app), base_url="http://test"
    ) as client:
        open_list = await _rpc(client, "tools/list", meta_bad, headers=unset_headers)
    assert "tools" in open_list.json()["result"]


async def test_require_key_access_empty_catalog_without_grant(settings, monkeypatch):
    """Flag on + VK with no metadata.mcp grant → empty tools/list (#1352)."""
    settings.integrations.mcp_policy.require_key_access_defined = True
    app, headers, _ = _app_with_key(settings, monkeypatch)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        listed = await _rpc(client, "tools/list", headers=headers)
        denied = await _rpc(
            client, "tools/call", {"name": "route", "arguments": {"input": "hi"}}, headers=headers
        )
        legacy = await client.post("/v1/mcp/query", json={"tool": "tools/list"}, headers=headers)
    assert listed.json()["result"]["tools"] == []
    assert denied.json()["error"]["code"] == TOOL_DENIED
    assert legacy.json()["result"]["tools"] == []


async def test_require_key_access_granted_key_keeps_policy(settings, monkeypatch):
    """Flag on + explicit metadata.mcp.allow keeps normal allow/deny (#1352)."""
    settings.integrations.mcp_policy.require_key_access_defined = True
    app, headers, _ = _app_with_key(
        settings, monkeypatch, metadata={"mcp": {"allow": ["route"]}}
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        listed = await _rpc(client, "tools/list", headers=headers)
        allowed = await _rpc(
            client, "tools/call", {"name": "route", "arguments": {"input": "hi"}}, headers=headers
        )
    names = {tool["name"] for tool in listed.json()["result"]["tools"]}
    assert names == {"route"}
    assert allowed.json()["result"]["content"][0]["text"] == "routed"


async def test_require_key_access_flag_off_unchanged(settings, monkeypatch):
    """Default off: VK without metadata.mcp still sees the catalog (#1352)."""
    assert settings.integrations.mcp_policy.require_key_access_defined is False
    app, headers, _ = _app_with_key(settings, monkeypatch)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        listed = await _rpc(client, "tools/list", headers=headers)
    names = {tool["name"] for tool in listed.json()["result"]["tools"]}
    assert "route" in names
    assert "stats" in names


async def test_require_key_access_master_key_unchanged(settings, monkeypatch):
    """Master key ignores require_key_access_defined (#1352)."""
    settings.server.api_key = "sekret"
    settings.integrations.mcp_policy.require_key_access_defined = True
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)

    async def fake_execute(_request: InternalRequest) -> InternalResponse:
        return InternalResponse(
            content="routed",
            model="llama3.2:3b",
            daari_meta=DaariMeta(tier="L3", executor="ollama", provider_id="ollama:l3"),
        )

    mock_all_ollama_executors(monkeypatch, app.state.ctx.router, fake_execute)
    headers = {"Authorization": "Bearer sekret"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        listed = await _rpc(client, "tools/list", headers=headers)
        allowed = await _rpc(
            client, "tools/call", {"name": "route", "arguments": {"input": "hi"}}, headers=headers
        )
    names = {tool["name"] for tool in listed.json()["result"]["tools"]}
    assert "route" in names
    assert allowed.json()["result"]["content"][0]["text"] == "routed"


async def test_require_key_access_servers_only_grant_keeps_catalog(settings, monkeypatch):
    """Flag on + metadata.mcp.servers.allow is a grant: first-party tools stay listed (#1362)."""
    settings.integrations.mcp_policy.require_key_access_defined = True
    app, headers, _ = _app_with_key(
        settings, monkeypatch, metadata={"mcp": {"servers": {"allow": ["weather"]}}}
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        listed = await _rpc(client, "tools/list", headers=headers)
        allowed = await _rpc(
            client, "tools/call", {"name": "route", "arguments": {"input": "hi"}}, headers=headers
        )
    names = {tool["name"] for tool in listed.json()["result"]["tools"]}
    assert names
    assert "route" in names
    assert "stats" in names
    assert allowed.json()["result"]["content"][0]["text"] == "routed"


async def test_require_key_access_clients_only_is_not_a_grant(settings, monkeypatch):
    """Flag on + metadata.mcp.clients alone still fail-closes (#1362)."""
    settings.integrations.mcp_policy.require_key_access_defined = True
    app, headers, _ = _app_with_key(
        settings,
        monkeypatch,
        metadata={"mcp": {"clients": {"allow": ["claude-code"], "deny": []}}},
    )
    params = {
        "_meta": {
            "io.modelcontextprotocol/clientInfo": {"name": "claude-code", "version": "0"},
        }
    }
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        listed = await _rpc(client, "tools/list", params, headers=headers)
        denied = await _rpc(
            client,
            "tools/call",
            {"name": "route", "arguments": {"input": "hi"}, **params},
            headers=headers,
        )
        legacy = await client.post("/v1/mcp/query", json={"tool": "tools/list"}, headers=headers)
    assert listed.json()["result"]["tools"] == []
    assert denied.json()["error"]["code"] == TOOL_DENIED
    assert legacy.json()["result"]["tools"] == []
