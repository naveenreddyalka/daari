"""MCP notifications/cancelled — egress emit + ingress honor (#2265)."""

from __future__ import annotations

import asyncio
import json
import socket

import httpx
import pytest
from httpx import ASGITransport, AsyncClient

from daari.gateway.internal import InternalRequest, Message
from daari.providers.mcp_egress import McpEgressProvider, McpServerConfig
from daari.router.router import AppContext
from daari.server.app import create_app
from tests.conftest import META_HEADERS


@pytest.fixture(autouse=True)
def _public_dns_for_fake_mcp_hosts(monkeypatch):
    def fake_getaddrinfo(host, port, *args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port or 0))]

    monkeypatch.setattr("daari.security.egress_url.socket.getaddrinfo", fake_getaddrinfo)


def _app(settings):
    application = create_app(settings)
    application.state.ctx = AppContext.from_settings(settings)
    return application


@pytest.mark.asyncio
async def test_egress_sends_notifications_cancelled_on_abort(monkeypatch):
    """Cancelled call_tool POSTs notifications/cancelled with the JSON-RPC id."""
    seen: list[dict] = []
    call_started = asyncio.Event()
    release_call = asyncio.Event()
    events: list[tuple[str, dict]] = []

    def capture(event: str, payload: dict) -> None:
        events.append((event, dict(payload)))

    monkeypatch.setattr("daari.gateway.request_log.log_gateway_event", capture)

    async def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode("utf-8"))
        seen.append(body)
        method = body.get("method")
        if method == "tools/call":
            call_started.set()
            await release_call.wait()
            return httpx.Response(
                200,
                json={
                    "jsonrpc": "2.0",
                    "id": body.get("id"),
                    "result": {"content": [{"type": "text", "text": "late"}]},
                },
            )
        if method == "notifications/cancelled":
            return httpx.Response(202)
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": body.get("id"), "result": {}})

    class Patched(httpx.AsyncClient):
        def __init__(self, *args, **kwargs):
            kwargs["transport"] = httpx.MockTransport(
                lambda req: httpx.Response(500)  # unused; we override post
            )
            super().__init__(*args, **kwargs)

        async def post(self, url, **kwargs):  # type: ignore[override]
            content = kwargs.get("content")
            if content is None and "json" in kwargs:
                content = json.dumps(kwargs["json"]).encode("utf-8")
            req = httpx.Request("POST", url, headers=kwargs.get("headers"), content=content)
            return await handler(req)

    monkeypatch.setattr(httpx, "AsyncClient", Patched)
    provider = McpEgressProvider(McpServerConfig(id="demo", url="http://mcp.test/rpc"))

    task = asyncio.create_task(
        provider.call_tool(
            InternalRequest(
                messages=[Message(role="user", content="hi")],
                model="daari",
            ),
            tool="slow",
            arguments={"q": 1},
        )
    )
    await asyncio.wait_for(call_started.wait(), timeout=2.0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    release_call.set()

    cancelled = [b for b in seen if b.get("method") == "notifications/cancelled"]
    assert len(cancelled) == 1
    note = cancelled[0]
    assert "id" not in note  # JSON-RPC notification
    assert note["params"]["requestId"] == seen[0]["id"]
    assert any(e[0] == "mcp.egress_cancelled" for e in events)


@pytest.mark.asyncio
async def test_egress_cancel_notification_failure_does_not_mask(monkeypatch):
    """Best-effort: notify failure must not swallow CancelledError."""
    call_started = asyncio.Event()

    async def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode("utf-8"))
        if body.get("method") == "tools/call":
            call_started.set()
            await asyncio.sleep(30)
            return httpx.Response(200, json={"jsonrpc": "2.0", "id": 1, "result": {}})
        raise httpx.ConnectError("notify failed")

    class Patched(httpx.AsyncClient):
        def __init__(self, *args, **kwargs):
            kwargs["transport"] = httpx.MockTransport(lambda _r: httpx.Response(500))
            super().__init__(*args, **kwargs)

        async def post(self, url, **kwargs):  # type: ignore[override]
            content = kwargs.get("content")
            if content is None and "json" in kwargs:
                content = json.dumps(kwargs["json"]).encode("utf-8")
            req = httpx.Request("POST", url, headers=kwargs.get("headers"), content=content)
            return await handler(req)

    monkeypatch.setattr(httpx, "AsyncClient", Patched)
    provider = McpEgressProvider(McpServerConfig(id="demo", url="http://mcp.test/rpc"))
    task = asyncio.create_task(
        provider.call_tool(
            InternalRequest(messages=[Message(role="user", content="hi")], model="daari"),
            tool="slow",
            arguments={},
        )
    )
    await asyncio.wait_for(call_started.wait(), timeout=2.0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


@pytest.mark.asyncio
async def test_egress_completed_call_unchanged(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode("utf-8"))
        assert body["method"] == "tools/call"
        return httpx.Response(
            200,
            json={
                "jsonrpc": "2.0",
                "id": body["id"],
                "result": {"content": [{"type": "text", "text": "ok"}]},
            },
        )

    class Patched(httpx.AsyncClient):
        def __init__(self, *args, **kwargs):
            kwargs["transport"] = httpx.MockTransport(handler)
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", Patched)
    provider = McpEgressProvider(McpServerConfig(id="demo", url="http://mcp.test/rpc"))
    result = await provider.call_tool(
        InternalRequest(messages=[Message(role="user", content="hi")], model="daari"),
        tool="ping",
        arguments={},
    )
    assert "ok" in result.content


@pytest.mark.asyncio
async def test_ingress_notifications_cancelled_stops_inflight(settings, monkeypatch):
    """Matching requestId cancels tools/call; no JSON-RPC result for that id."""
    app = _app(settings)
    gate = asyncio.Event()
    saw_cancel = asyncio.Event()
    events: list[tuple[str, dict]] = []

    def capture(event: str, payload: dict) -> None:
        events.append((event, dict(payload)))

    monkeypatch.setattr("daari.gateway.mcp_activity.log_gateway_event", capture)

    async def blocked_health(*_a, **_k):
        gate.set()
        try:
            await asyncio.sleep(30)
        except asyncio.CancelledError:
            saw_cancel.set()
            raise
        from daari.gateway.mcp import MCPQueryResponse

        return MCPQueryResponse(tool="health", result={"status": "ok"})

    monkeypatch.setattr("daari.gateway.mcp._run_tool", blocked_health)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        call_task = asyncio.create_task(
            client.post(
                "/mcp",
                json={
                    "jsonrpc": "2.0",
                    "id": 42,
                    "method": "tools/call",
                    "params": {"name": "health", "arguments": {}},
                },
                headers={**META_HEADERS, "X-Request-ID": "mcp-cancel-42"},
            )
        )
        await asyncio.wait_for(gate.wait(), timeout=2.0)
        for _ in range(50):
            registry = app.state.ctx.mcp_activity
            if registry.get_by_rpc_id(42) is not None or registry.get("mcp-cancel-42"):
                break
            await asyncio.sleep(0.02)

        note = await client.post(
            "/mcp",
            json={
                "jsonrpc": "2.0",
                "method": "notifications/cancelled",
                "params": {"requestId": 42},
            },
            headers=META_HEADERS,
        )
        assert note.status_code == 202
        response = await call_task
        # Spec: no JSON-RPC result for the cancelled request id.
        assert response.status_code in {204, 499}
        if response.content:
            body = response.json()
            assert body.get("id") != 42 or "result" not in body
        assert saw_cancel.is_set()
        assert any(e[0] == "mcp.request_cancelled" for e in events)


@pytest.mark.asyncio
async def test_ingress_notifications_cancelled_unknown_id_ignored(settings):
    app = _app(settings)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        note = await client.post(
            "/mcp",
            json={
                "jsonrpc": "2.0",
                "method": "notifications/cancelled",
                "params": {"requestId": "never-existed"},
            },
            headers=META_HEADERS,
        )
        assert note.status_code == 202


@pytest.mark.asyncio
async def test_tasks_cancel_still_works(settings, tmp_path, monkeypatch):
    """Regression: tasks/cancel path unchanged (#2265 AC)."""
    from daari.gateway.internal import DaariMeta, InternalResponse
    from daari.gateway.mcp_tasks import TASKS_META_KEY
    from tests.conftest import mock_all_ollama_executors
    from tests.unit.test_mcp_tasks import _rpc

    settings.integrations.mcp_tasks.path = str(tmp_path / "mcp-tasks")
    app = _app(settings)
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
