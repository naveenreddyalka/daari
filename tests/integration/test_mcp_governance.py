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
    app, headers, _ = _app_with_key(settings, monkeypatch, metadata={"mcp": {"deny": ["stats"]}})
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await _rpc(
            client,
            "tools/call",
            {"name": "route", "arguments": {"input": "hi"}},
            headers={**headers, "Mcp-Method": "tools/call", "Mcp-Name": "stats"},
        )
    assert response.json()["error"]["code"] == TOOL_DENIED
