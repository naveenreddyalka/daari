"""GET /v1/daari/stats exposes MCP tool and task summaries (#941)."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from daari.gateway.mcp_tasks import McpTaskStore
from daari.router.router import AppContext
from daari.server.app import create_app


def _app(settings):
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    return app


@pytest.mark.asyncio
async def test_stats_includes_mcp_tool_calls_and_tasks(settings):
    app = _app(settings)
    app.state.ctx.metrics.record_mcp_tool_call(tool="route", outcome="ok")
    app.state.ctx.metrics.record_mcp_tool_call(tool="stats", outcome="deny")
    store = McpTaskStore()
    working = store.create(tool="route")
    store.fail(store.create(tool="stats").task_id, "boom")
    assert working.status == "working"
    app.state.ctx.mcp_task_store = store

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/v1/daari/stats")

    assert response.status_code == 200
    body = response.json()
    assert body["mcp_tool_calls"]["route:ok"] == 1
    assert body["mcp_tool_calls"]["stats:deny"] == 1
    assert body["mcp_tasks"]["working"] == 1
    assert body["mcp_tasks"]["failed"] == 1
    assert body["mcp_tasks"]["active"] == 1
    assert body["mcp_tasks"]["total"] == 2


def test_mcp_task_store_snapshot_empty():
    snap = McpTaskStore().snapshot()
    assert snap["working"] == 0
    assert snap["active"] == 0
    assert snap["total"] == 0
