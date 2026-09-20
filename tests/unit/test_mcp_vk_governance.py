"""Virtual-key governance on MCP tools/call route (#839)."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from daari.auth.virtual_keys import VirtualKeyStore
from daari.enterprise.audit import AuditLog
from daari.gateway.internal import DaariMeta, InternalRequest, InternalResponse
from daari.router.router import AppContext
from daari.server.app import create_app
from tests.conftest import mock_all_ollama_executors

pytestmark = pytest.mark.asyncio


def _app_with_key(settings, monkeypatch, *, allowed_models=None, cache_scope=None, team=None):
    settings.server.api_key = "master"
    store = VirtualKeyStore(settings.virtual_keys_path)
    if team:
        store.create_team(team, cache_scope=cache_scope or "global")
    created = store.create(
        "agent",
        client_id="agent",
        team=team,
        allowed_models=allowed_models,
        cache_scope=cache_scope,
        tier_cap="L4",
    )
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    app.state.virtual_key_store = store
    app.state.ctx.virtual_key_store = store
    captured: list[InternalRequest] = []

    async def fake_execute(request: InternalRequest) -> InternalResponse:
        captured.append(request)
        return InternalResponse(
            content="routed",
            model=request.model or "llama3.2:3b",
            daari_meta=DaariMeta(tier="L3", executor="ollama", provider_id="ollama:l3"),
        )

    mock_all_ollama_executors(monkeypatch, app.state.ctx.router, fake_execute)
    headers = {"Authorization": f"Bearer {created.plaintext}"}
    return app, headers, created, captured


async def _rpc(client, method, params=None, *, headers, rpc_id=1):
    body = {"jsonrpc": "2.0", "id": rpc_id, "method": method}
    if params is not None:
        body["params"] = params
    return await client.post("/mcp", json=body, headers=headers)


async def test_mcp_route_inherits_virtual_key_claims(settings, monkeypatch):
    app, headers, created, captured = _app_with_key(
        settings, monkeypatch, team="eng", cache_scope="key"
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        rpc = await _rpc(
            client,
            "tools/call",
            {"name": "route", "arguments": {"input": "hi"}},
            headers=headers,
        )
        legacy = await client.post(
            "/v1/mcp/query",
            json={"tool": "route", "input": "hi again"},
            headers=headers,
        )
    assert rpc.status_code == 200, rpc.text
    assert legacy.status_code == 200, legacy.text
    assert captured
    for request in captured:
        meta = request.meta
        assert meta.key_id == created.key.key_id
        assert meta.team_id == created.key.team_id
        assert meta.tier_cap == "L4"
        assert meta.cache_scope == "key"
        assert meta.client_id == "agent"
    contents = {request.messages[0].content for request in captured}
    assert "hi" in contents
    assert "hi again" in contents


async def test_mcp_disallowed_model_is_403_with_audit(settings, monkeypatch, tmp_path):
    settings.enterprise.audit_path = str(tmp_path / "audit.sqlite3")
    app, headers, created, captured = _app_with_key(
        settings, monkeypatch, allowed_models=["claude-*"]
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        rpc = await _rpc(
            client,
            "tools/call",
            {"name": "route", "arguments": {"input": "hi", "model": "gpt-4o"}},
            headers=headers,
        )
        legacy = await client.post(
            "/v1/mcp/query",
            json={"tool": "route", "input": "hi", "model": "gpt-4o"},
            headers=headers,
        )
        default_denied = await _rpc(
            client,
            "tools/call",
            {"name": "route", "arguments": {"input": "default-l3"}},
            headers=headers,
        )
    assert rpc.status_code == 403, rpc.text
    assert "model_not_allowed" in rpc.text
    assert "gpt-4o" in rpc.text
    assert created.plaintext not in rpc.text
    assert legacy.status_code == 403, legacy.text
    assert "model_not_allowed" in legacy.text
    assert default_denied.status_code == 403, default_denied.text
    assert "llama3.2:3b" in default_denied.text or "model_not_allowed" in default_denied.text
    assert captured == []
    rows = AuditLog(settings.enterprise.audit_path).list(action="auth.model_denied")
    assert len(rows) >= 2
    assert all(row["detail"].get("model") for row in rows)
    assert created.plaintext not in str(rows)


async def test_mcp_spend_attributed_to_key_and_team(settings, monkeypatch, tmp_path):
    settings.usage.spend.enabled = True
    settings.usage.spend.path = str(tmp_path / "spend.sqlite3")
    app, headers, created, _ = _app_with_key(settings, monkeypatch, team="eng")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await _rpc(
            client,
            "tools/call",
            {"name": "route", "arguments": {"input": "bill me"}},
            headers=headers,
        )
    assert response.status_code == 200, response.text
    rows = list(app.state.ctx.router.spend_ledger.iter_rows(since="2000-01-01T00:00:00+00:00"))
    assert len(rows) >= 1
    assert rows[0]["key_id"] == created.key.key_id
    assert rows[0]["team_id"] == created.key.team_id


async def test_mcp_route_cache_does_not_cross_key_scopes(settings, monkeypatch):
    settings.cache.l0.enabled = True
    settings.cache.l1.enabled = False
    settings.server.api_key = "master"
    store = VirtualKeyStore(settings.virtual_keys_path)
    left = store.create("left", client_id="left", cache_scope="key")
    right = store.create("right", client_id="right", cache_scope="key")
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    app.state.virtual_key_store = store
    app.state.ctx.virtual_key_store = store
    calls: list[str] = []

    async def fake_execute(request: InternalRequest) -> InternalResponse:
        calls.append(request.meta.key_id or "")
        return InternalResponse(
            content=f"for-{request.meta.key_id}",
            model="llama3.2:3b",
            daari_meta=DaariMeta(tier="L3", executor="ollama", provider_id="ollama:l3"),
        )

    mock_all_ollama_executors(monkeypatch, app.state.ctx.router, fake_execute)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        first = await _rpc(
            client,
            "tools/call",
            {"name": "route", "arguments": {"input": "same prompt"}},
            headers={"Authorization": f"Bearer {left.plaintext}"},
        )
        second = await _rpc(
            client,
            "tools/call",
            {"name": "route", "arguments": {"input": "same prompt"}},
            headers={"Authorization": f"Bearer {right.plaintext}"},
            rpc_id=2,
        )
        again = await _rpc(
            client,
            "tools/call",
            {"name": "route", "arguments": {"input": "same prompt"}},
            headers={"Authorization": f"Bearer {left.plaintext}"},
            rpc_id=3,
        )
    assert first.status_code == 200 and second.status_code == 200 and again.status_code == 200
    assert first.json()["result"]["content"][0]["text"] == f"for-{left.key.key_id}"
    assert second.json()["result"]["content"][0]["text"] == f"for-{right.key.key_id}"
    assert again.json()["result"]["content"][0]["text"] == f"for-{left.key.key_id}"
    assert calls.count(left.key.key_id) == 1
    assert calls.count(right.key.key_id) == 1
