"""MCP in-flight activity registry + admin force-abort (#1231)."""

from __future__ import annotations

import asyncio

import pytest
from httpx import ASGITransport, AsyncClient

from daari.enterprise.postgres_audit import audit_log_from_settings
from daari.gateway.mcp_activity import McpActivityRegistry
from daari.router.router import AppContext
from daari.server.app import create_app
from tests.conftest import META_HEADERS


def _app(settings):
    application = create_app(settings)
    application.state.ctx = AppContext.from_settings(settings)
    return application


@pytest.mark.asyncio
async def test_registry_register_list_unregister():
    registry = McpActivityRegistry()
    entry = registry.register(
        request_id="req-1",
        key_id="key-a",
        method="tools/call",
        tool_name="route",
    )
    assert entry.request_id == "req-1"
    listed = registry.list()
    assert len(listed) == 1
    assert listed[0]["request_id"] == "req-1"
    assert listed[0]["key_id"] == "key-a"
    assert listed[0]["method"] == "tools/call"
    assert listed[0]["tool_name"] == "route"
    assert "started_at" in listed[0]
    registry.unregister("req-1")
    assert registry.list() == []


@pytest.mark.asyncio
async def test_registry_abort_cancels_task_and_is_idempotent():
    registry = McpActivityRegistry()
    started = asyncio.Event()
    cancelled = asyncio.Event()

    async def slow() -> str:
        started.set()
        try:
            await asyncio.sleep(30)
        except asyncio.CancelledError:
            cancelled.set()
            raise
        return "done"

    task = asyncio.create_task(slow())
    registry.register(
        request_id="req-abort",
        key_id=None,
        method="tools/call",
        tool_name="health",
        task=task,
    )
    await started.wait()
    assert registry.abort("req-abort") is True
    with pytest.raises(asyncio.CancelledError):
        await task
    assert cancelled.is_set()
    assert registry.list() == []
    # Idempotent once finished / cleared.
    assert registry.abort("req-abort") is True
    assert registry.abort("missing") is None


@pytest.mark.asyncio
async def test_admin_list_shows_in_flight_tools_call(settings, monkeypatch):
    app = _app(settings)
    registry = getattr(app.state.ctx, "mcp_activity", None)
    assert registry is not None

    gate = asyncio.Event()

    async def blocked_health(*_a, **_k):
        await gate.wait()
        from daari.gateway.mcp import MCPQueryResponse

        return MCPQueryResponse(tool="health", result={"status": "ok", "adapter": "mcp"})

    monkeypatch.setattr("daari.gateway.mcp._run_tool", blocked_health)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        call_task = asyncio.create_task(
            client.post(
                "/mcp",
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "tools/call",
                    "params": {"name": "health", "arguments": {}},
                },
                headers={**META_HEADERS, "X-Request-ID": "mcp-inflight-1"},
            )
        )
        for _ in range(50):
            listed = await client.get("/v1/daari/mcp/activity")
            if listed.status_code == 200 and listed.json().get("activity"):
                break
            await asyncio.sleep(0.02)
        assert listed.status_code == 200
        activity = listed.json()["activity"]
        assert any(row["request_id"] == "mcp-inflight-1" for row in activity)
        row = next(r for r in activity if r["request_id"] == "mcp-inflight-1")
        assert row["method"] == "tools/call"
        assert row["tool_name"] == "health"
        gate.set()
        response = await call_task
        assert response.status_code == 200
        assert listed.json()  # sanity
        after = await client.get("/v1/daari/mcp/activity")
        assert after.status_code == 200
        assert not any(r["request_id"] == "mcp-inflight-1" for r in after.json()["activity"])


@pytest.mark.asyncio
async def test_admin_abort_cancels_in_flight_and_audits(settings, monkeypatch, tmp_path):
    settings.enterprise.audit_path = str(tmp_path / "audit.sqlite3")
    app = _app(settings)

    gate = asyncio.Event()
    saw_cancel = asyncio.Event()

    async def blocked_route(*_a, **_k):
        gate.set()
        try:
            await asyncio.sleep(30)
        except asyncio.CancelledError:
            saw_cancel.set()
            raise
        from daari.gateway.mcp import MCPQueryResponse

        return MCPQueryResponse(tool="route", result={"content": "never"})

    monkeypatch.setattr("daari.gateway.mcp._run_tool", blocked_route)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        call_task = asyncio.create_task(
            client.post(
                "/v1/mcp/query",
                json={"tool": "route", "input": "hi"},
                headers={**META_HEADERS, "X-Request-ID": "mcp-abort-me"},
            )
        )
        await gate.wait()
        for _ in range(50):
            listed = await client.get("/v1/daari/mcp/activity")
            if any(r["request_id"] == "mcp-abort-me" for r in listed.json().get("activity", [])):
                break
            await asyncio.sleep(0.02)
        abort = await client.post("/v1/daari/mcp/activity/mcp-abort-me/abort")
        assert abort.status_code == 200
        assert abort.json()["status"] in {"aborted", "already_finished"}
        response = await call_task
        assert response.status_code in {499, 200}
        assert saw_cancel.is_set() or response.status_code == 499
        # Unknown id → 404
        missing = await client.post("/v1/daari/mcp/activity/no-such-id/abort")
        assert missing.status_code == 404
        # Idempotent after finish
        again = await client.post("/v1/daari/mcp/activity/mcp-abort-me/abort")
        assert again.status_code == 200
        assert again.json()["status"] == "already_finished"

    audit = audit_log_from_settings(settings)
    entries = audit.list(limit=50)
    assert any(e.get("action") == "mcp.activity.abort" for e in entries)


@pytest.mark.asyncio
async def test_admin_abort_unknown_returns_404(settings):
    app = _app(settings)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/v1/daari/mcp/activity/does-not-exist/abort")
    assert response.status_code == 404
