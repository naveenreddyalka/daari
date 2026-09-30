"""Server-side MCP tool execution for Responses type=mcp (#1232)."""

from __future__ import annotations

import json
import socket

import httpx
import pytest
from httpx import ASGITransport, AsyncClient

from daari.config.settings import McpServerSettings
from daari.gateway.internal import DaariMeta, InternalRequest, InternalResponse
from daari.gateway.responses import unsupported_responses_tools
from daari.gateway.responses_mcp import (
    function_name_for,
    server_side_responses_enabled,
    validate_responses_mcp_tools,
)
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
    assert server_side_responses_enabled(settings) is False
    assert settings.integrations.mcp_egress.server_side_responses is False


def test_unsupported_still_lists_mcp_when_flag_off():
    bad = unsupported_responses_tools([{"type": "mcp", "server_label": "x"}])
    assert bad == ["mcp"]


def test_validate_rejects_mcp_when_flag_off():
    detail = validate_responses_mcp_tools(
        [{"type": "mcp", "server_label": "demo"}],
        enabled=False,
        configured_ids=frozenset({"demo"}),
    )
    assert detail is not None
    assert "mcp" in detail
    assert "function" in detail


def test_validate_rejects_unknown_server_when_enabled():
    detail = validate_responses_mcp_tools(
        [{"type": "mcp", "server_label": "nope"}],
        enabled=True,
        configured_ids=frozenset({"demo"}),
    )
    assert detail is not None
    assert "not configured" in detail
    assert "nope" in detail


def test_validate_allows_known_mcp_when_enabled():
    assert (
        validate_responses_mcp_tools(
            [
                {"type": "function", "name": "f", "parameters": {}},
                {"type": "mcp", "server_label": "demo"},
            ],
            enabled=True,
            configured_ids=frozenset({"demo"}),
        )
        is None
    )


@pytest.mark.asyncio
async def test_default_off_mcp_tool_returns_400(settings):
    settings.integrations.mcp_servers = [
        McpServerSettings(id="demo", url="http://mcp.test/rpc"),
    ]
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/responses",
            json={
                "model": "daari",
                "input": "hi",
                "tools": [{"type": "mcp", "server_label": "demo"}],
            },
        )
    assert response.status_code == 400
    assert "mcp" in response.json()["detail"]


@pytest.mark.asyncio
async def test_enabled_unknown_server_returns_400(settings):
    settings.integrations.mcp_egress.server_side_responses = True
    settings.integrations.mcp_servers = [
        McpServerSettings(id="demo", url="http://mcp.test/rpc"),
    ]
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/responses",
            json={
                "model": "daari",
                "input": "hi",
                "tools": [{"type": "mcp", "server_label": "missing"}],
            },
        )
    assert response.status_code == 400
    detail = response.json()["detail"]
    assert "not configured" in detail
    assert "missing" in detail


@pytest.mark.asyncio
async def test_enabled_executes_mocked_mcp_tool_round(settings, monkeypatch):
    settings.integrations.mcp_egress.server_side_responses = True
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
        # Second turn: tool result fed back.
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
            "/v1/responses",
            json={
                "model": "daari",
                "input": "ping please",
                "tools": [{"type": "mcp", "server_label": "demo"}],
            },
        )
    assert response.status_code == 200, response.text
    body = response.json()
    assert "done with pong" in json.dumps(body)
    assert any(b.get("method") == "tools/list" for b in seen)
    assert any(b.get("method") == "tools/call" for b in seen)
    assert calls["n"] == 2


@pytest.mark.asyncio
async def test_enabled_ssrf_blocks_private_url_before_post(settings, monkeypatch):
    settings.integrations.mcp_egress.server_side_responses = True
    settings.integrations.mcp_egress.allow_private_networks = False
    settings.integrations.mcp_servers = [
        McpServerSettings(id="meta", url="http://169.254.169.254/latest"),
    ]
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": 1, "result": {"tools": []}})

    monkeypatch.setattr(httpx, "AsyncClient", _patched_client(handler))
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)

    async def fake_route(request: InternalRequest) -> InternalResponse:
        return InternalResponse(
            content="should not matter",
            model="m",
            daari_meta=DaariMeta(tier="L3", executor="ollama", latency_ms=1),
        )

    app.state.ctx.router.route = fake_route
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/responses",
            json={
                "model": "daari",
                "input": "hi",
                "tools": [{"type": "mcp", "server_label": "meta"}],
            },
        )
    assert seen == []
    assert response.status_code == 400
    assert "egress" in response.json()["detail"].lower() or "private" in response.json()[
        "detail"
    ].lower() or "blocked" in response.json()["detail"].lower() or "not allowed" in response.json()[
        "detail"
    ].lower()


@pytest.mark.asyncio
async def test_enabled_denied_server_policy_blocks_before_post(settings, monkeypatch):
    settings.integrations.mcp_egress.server_side_responses = True
    settings.integrations.mcp_servers = [
        McpServerSettings(id="shell", url="http://mcp.test/rpc"),
    ]
    settings.integrations.mcp_policy.servers.deny = ["shell"]
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": 1, "result": {"tools": []}})

    monkeypatch.setattr(httpx, "AsyncClient", _patched_client(handler))
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)

    async def fake_route(request: InternalRequest) -> InternalResponse:
        return InternalResponse(
            content="unreachable",
            model="m",
            daari_meta=DaariMeta(tier="L3", executor="ollama", latency_ms=1),
        )

    app.state.ctx.router.route = fake_route
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/responses",
            json={
                "model": "daari",
                "input": "hi",
                "tools": [{"type": "mcp", "server_label": "shell"}],
            },
        )
    assert seen == []
    assert response.status_code == 400
    detail = response.json()["detail"].lower()
    assert "denied" in detail or "shell" in detail
