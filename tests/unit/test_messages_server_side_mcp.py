"""Server-side MCP for Messages mcp_servers + mcp_toolset (#1261)."""

from __future__ import annotations

import json
import socket

import httpx
import pytest
from httpx import ASGITransport, AsyncClient

from daari.config.settings import McpServerSettings
from daari.gateway.internal import DaariMeta, InternalRequest, InternalResponse
from daari.gateway.messages_mcp import (
    mcp_tools_from_messages,
    server_side_messages_enabled,
    validate_messages_mcp,
)
from daari.gateway.responses_mcp import function_name_for
from daari.router.router import AppContext
from daari.server.app import create_app


@pytest.fixture(autouse=True)
def _public_dns_for_fake_mcp_hosts(monkeypatch):
    def fake_getaddrinfo(host, port, *args, **kwargs):
        return [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port or 0))
        ]

    monkeypatch.setattr("daari.security.egress_url.socket.getaddrinfo", fake_getaddrinfo)


def _patched_client(handler):
    class Patched(httpx.AsyncClient):
        def __init__(self, *args, **kwargs):
            kwargs["transport"] = httpx.MockTransport(handler)
            super().__init__(*args, **kwargs)

    return Patched


def test_flag_defaults_off(settings):
    assert server_side_messages_enabled(settings) is False
    assert settings.integrations.mcp_egress.server_side_messages is False


def test_validate_rejects_when_flag_off():
    detail = validate_messages_mcp(
        mcp_servers=[{"type": "url", "name": "demo", "url": "https://x"}],
        tools=[{"type": "mcp_toolset", "mcp_server_name": "demo"}],
        enabled=False,
        configured_ids=frozenset({"demo"}),
    )
    assert detail is not None
    assert "server_side_messages" in detail


def test_validate_rejects_unknown_server_when_enabled():
    detail = validate_messages_mcp(
        mcp_servers=[{"name": "nope"}],
        tools=[{"type": "mcp_toolset", "mcp_server_name": "nope"}],
        enabled=True,
        configured_ids=frozenset({"demo"}),
    )
    assert detail is not None
    assert "not configured" in detail
    assert "nope" in detail


def test_validate_allows_known_when_enabled():
    assert (
        validate_messages_mcp(
            mcp_servers=[{"name": "demo"}],
            tools=[{"type": "mcp_toolset", "mcp_server_name": "demo"}],
            enabled=True,
            configured_ids=frozenset({"demo"}),
        )
        is None
    )


def test_mcp_tools_from_messages_maps_toolset():
    tools = mcp_tools_from_messages(
        mcp_servers=[{"name": "demo"}],
        tools=[{"type": "mcp_toolset", "mcp_server_name": "demo"}],
    )
    assert tools == [{"type": "mcp", "server_label": "demo"}]


@pytest.mark.asyncio
async def test_default_off_mcp_toolset_returns_400(settings):
    settings.integrations.mcp_servers = [
        McpServerSettings(id="demo", url="http://mcp.test/rpc"),
    ]
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/messages",
            json={
                "model": "daari",
                "max_tokens": 50,
                "messages": [{"role": "user", "content": "hi"}],
                "mcp_servers": [
                    {"type": "url", "name": "demo", "url": "https://example.com/mcp"}
                ],
                "tools": [{"type": "mcp_toolset", "mcp_server_name": "demo"}],
            },
        )
    assert response.status_code == 400
    assert "server_side_messages" in response.json()["detail"]


@pytest.mark.asyncio
async def test_enabled_unknown_server_returns_400(settings):
    settings.integrations.mcp_egress.server_side_messages = True
    settings.integrations.mcp_servers = [
        McpServerSettings(id="demo", url="http://mcp.test/rpc"),
    ]
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/messages",
            json={
                "model": "daari",
                "max_tokens": 50,
                "messages": [{"role": "user", "content": "hi"}],
                "mcp_servers": [
                    {"type": "url", "name": "missing", "url": "https://example.com/mcp"}
                ],
                "tools": [{"type": "mcp_toolset", "mcp_server_name": "missing"}],
            },
        )
    assert response.status_code == 400
    detail = response.json()["detail"]
    assert "not configured" in detail
    assert "missing" in detail


@pytest.mark.asyncio
async def test_enabled_executes_mocked_mcp_tool_round(settings, monkeypatch):
    settings.integrations.mcp_egress.server_side_messages = True
    settings.integrations.mcp_servers = [
        McpServerSettings(id="demo", url="http://mcp.test/rpc"),
    ]
    seen: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode())
        seen.append(body)
        method = body.get("method")
        if method == "tools/list":
            return httpx.Response(
                200,
                json={
                    "jsonrpc": "2.0",
                    "id": body.get("id", 1),
                    "result": {
                        "tools": [
                            {
                                "name": "ping",
                                "description": "ping tool",
                                "inputSchema": {"type": "object", "properties": {}},
                            }
                        ]
                    },
                },
            )
        assert method == "tools/call"
        assert body["params"]["name"] == "ping"
        return httpx.Response(
            200,
            json={
                "jsonrpc": "2.0",
                "id": body.get("id", 1),
                "result": {"content": [{"type": "text", "text": "pong"}]},
            },
        )

    monkeypatch.setattr(httpx, "AsyncClient", _patched_client(handler))
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    fn = function_name_for("demo", "ping")
    calls = {"n": 0}

    async def fake_route(request: InternalRequest) -> InternalResponse:
        calls["n"] += 1
        if calls["n"] == 1:
            assert any(
                (t.get("function") or {}).get("name") == fn for t in (request.tools or [])
            )
            return InternalResponse(
                content="",
                model="m",
                tool_calls=[
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {"name": fn, "arguments": "{}"},
                    }
                ],
                daari_meta=DaariMeta(tier="L3", executor="ollama", latency_ms=1),
            )
        assert any(m.role == "tool" for m in request.messages)
        tool_msgs = [m for m in request.messages if m.role == "tool"]
        assert any("pong" in (m.content or "") for m in tool_msgs)
        return InternalResponse(
            content="done with pong",
            model="m",
            daari_meta=DaariMeta(tier="L3", executor="ollama", latency_ms=1),
        )

    app.state.ctx.router.route = fake_route
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/messages",
            json={
                "model": "daari",
                "max_tokens": 50,
                "messages": [{"role": "user", "content": "ping please"}],
                "mcp_servers": [
                    {"type": "url", "name": "demo", "url": "https://example.com/mcp"}
                ],
                "tools": [{"type": "mcp_toolset", "mcp_server_name": "demo"}],
            },
        )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["content"][0]["text"] == "done with pong"
    assert calls["n"] == 2
    assert any(item.get("method") == "tools/call" for item in seen)
