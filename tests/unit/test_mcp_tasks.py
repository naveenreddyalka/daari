"""MCP Tasks extension (SEP-2663 / #289)."""

from __future__ import annotations

import asyncio

import pytest
from httpx import ASGITransport, AsyncClient

from daari.gateway.internal import DaariMeta, InternalRequest, InternalResponse
from daari.gateway.mcp_tasks import (
    TASKS_CAPABILITY,
    TASKS_META_KEY,
    client_opted_into_tasks,
    initialize_capabilities,
    tool_should_become_task,
)
from daari.router.router import AppContext
from daari.server.app import create_app
from tests.conftest import META_HEADERS, mock_all_ollama_executors


def _app(settings, tmp_path):
    settings.integrations.mcp_tasks.path = str(tmp_path / "mcp-tasks")
    application = create_app(settings)
    application.state.ctx = AppContext.from_settings(settings)
    return application


async def _rpc(client, method, params=None, *, rpc_id=1):
    body = {"jsonrpc": "2.0", "id": rpc_id, "method": method}
    if params is not None:
        body["params"] = params
    return await client.post("/mcp", json=body, headers=META_HEADERS)


def test_capabilities_advertise_tasks_on_2026_07_28():
    caps = initialize_capabilities("2026-07-28")
    assert TASKS_CAPABILITY in caps
    assert "tools" in caps


def test_capabilities_omit_tasks_on_older_protocol():
    assert TASKS_CAPABILITY not in initialize_capabilities("2025-03-26")


def test_client_opt_in_detection():
    assert client_opted_into_tasks({"_meta": {TASKS_META_KEY: True}})
    assert client_opted_into_tasks({"_meta": {TASKS_META_KEY: {}}})
    assert not client_opted_into_tasks({"_meta": {}})
    assert not client_opted_into_tasks({})


def test_long_running_and_threshold_eligibility():
    assert tool_should_become_task("route", long_running_tools=["route"], threshold_ms=0)
    assert not tool_should_become_task("stats", long_running_tools=["route"], threshold_ms=0)
    assert tool_should_become_task("stats", long_running_tools=["route"], threshold_ms=1000)


@pytest.mark.asyncio
async def test_initialize_advertises_tasks_capability(settings, tmp_path):
    transport = ASGITransport(app=_app(settings, tmp_path))
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await _rpc(
            client,
            "initialize",
            {
                "protocolVersion": "2026-07-28",
                "capabilities": {},
                "clientInfo": {"name": "test", "version": "0"},
            },
        )
    caps = response.json()["result"]["capabilities"]
    assert TASKS_CAPABILITY in caps


@pytest.mark.asyncio
async def test_tools_call_without_opt_in_stays_blocking(settings, tmp_path, monkeypatch):
    app = _app(settings, tmp_path)

    async def fake_execute(request: InternalRequest) -> InternalResponse:
        return InternalResponse(
            content="blocked-ok",
            model="llama3.2:3b",
            daari_meta=DaariMeta(tier="L3", executor="ollama", provider_id="ollama", latency_ms=1),
        )

    mock_all_ollama_executors(monkeypatch, app.state.ctx.router, fake_execute)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await _rpc(
            client,
            "tools/call",
            {"name": "route", "arguments": {"input": "hello"}},
        )
    result = response.json()["result"]
    assert "taskId" not in result
    assert "content" in result


@pytest.mark.asyncio
async def test_opt_in_creates_task_and_polls_to_completion(settings, tmp_path, monkeypatch):
    app = _app(settings, tmp_path)
    started = asyncio.Event()
    release = asyncio.Event()

    async def fake_execute(request: InternalRequest) -> InternalResponse:
        started.set()
        await release.wait()
        return InternalResponse(
            content="task-done",
            model="llama3.2:3b",
            daari_meta=DaariMeta(tier="L3", executor="ollama", provider_id="ollama", latency_ms=1),
        )

    mock_all_ollama_executors(monkeypatch, app.state.ctx.router, fake_execute)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        created = await _rpc(
            client,
            "tools/call",
            {
                "name": "route",
                "arguments": {"input": "long job"},
                "_meta": {TASKS_META_KEY: True},
            },
        )
        body = created.json()["result"]
        assert "taskId" in body
        assert body["status"] == "working"
        task_id = body["taskId"]
        await asyncio.wait_for(started.wait(), timeout=2)
        mid = await _rpc(client, "tasks/get", {"taskId": task_id})
        assert mid.json()["result"]["status"] == "working"
        release.set()
        for _ in range(50):
            poll = await _rpc(client, "tasks/get", {"taskId": task_id})
            if poll.json()["result"]["status"] == "completed":
                break
            await asyncio.sleep(0.05)
        else:
            pytest.fail("task did not complete")
        assert "task-done" in json_dumps_result(poll.json()["result"]["result"])


def json_dumps_result(result) -> str:
    import json

    return json.dumps(result)


@pytest.mark.asyncio
async def test_tasks_cancel(settings, tmp_path, monkeypatch):
    app = _app(settings, tmp_path)
    gate = asyncio.Event()

    async def fake_execute(request: InternalRequest) -> InternalResponse:
        await gate.wait()
        return InternalResponse(
            content="should-not-matter",
            model="llama3.2:3b",
            daari_meta=DaariMeta(tier="L3", executor="ollama", provider_id="ollama", latency_ms=1),
        )

    mock_all_ollama_executors(monkeypatch, app.state.ctx.router, fake_execute)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        created = await _rpc(
            client,
            "tools/call",
            {
                "name": "route",
                "arguments": {"input": "cancel me"},
                "_meta": {TASKS_META_KEY: True},
            },
        )
        task_id = created.json()["result"]["taskId"]
        cancelled = await _rpc(client, "tasks/cancel", {"taskId": task_id})
        assert cancelled.json()["result"]["status"] == "cancelled"
        gate.set()


@pytest.mark.asyncio
async def test_tasks_update_reports_state(settings, tmp_path, monkeypatch):
    app = _app(settings, tmp_path)

    async def fake_execute(request: InternalRequest) -> InternalResponse:
        return InternalResponse(
            content="ok",
            model="llama3.2:3b",
            daari_meta=DaariMeta(tier="L3", executor="ollama", provider_id="ollama", latency_ms=1),
        )

    mock_all_ollama_executors(monkeypatch, app.state.ctx.router, fake_execute)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        created = await _rpc(
            client,
            "tools/call",
            {
                "name": "route",
                "arguments": {"input": "x"},
                "_meta": {TASKS_META_KEY: True},
            },
        )
        task_id = created.json()["result"]["taskId"]
        updated = await _rpc(client, "tasks/update", {"taskId": task_id})
        assert "status" in updated.json()["result"]
