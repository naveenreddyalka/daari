"""Opt-in /mcp tools/list aggregation from mcp_servers (#1294)."""

from __future__ import annotations

import json
import socket

import httpx
import pytest
from httpx import ASGITransport, AsyncClient

from daari.config.settings import McpServerSettings
from daari.gateway.mcp import ingress_aggregate_egress_enabled
from daari.gateway.mcp_policy import TOOL_DENIED
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


def _app(settings):
    application = create_app(settings)
    application.state.ctx = AppContext.from_settings(settings)
    return application


def test_flag_defaults_off(settings):
    assert ingress_aggregate_egress_enabled(settings) is False
    assert settings.integrations.mcp_aggregate_egress.enabled is False


@pytest.mark.asyncio
async def test_default_off_catalog_unchanged(settings, monkeypatch):
    settings.integrations.mcp_servers = [
        McpServerSettings(id="demo", url="http://mcp.test/rpc"),
    ]
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.host)
        return httpx.Response(500, json={"error": "should not be called"})

    monkeypatch.setattr(httpx, "AsyncClient", _patched_client(handler))
    app = _app(settings)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
        )
    assert response.status_code == 200
    names = {t["name"] for t in response.json()["result"]["tools"]}
    assert "route" in names
    assert "stats" in names
    assert function_name_for("demo", "ping") not in names
    assert not seen


@pytest.mark.asyncio
async def test_enabled_merges_and_routes_call(settings, monkeypatch):
    settings.integrations.mcp_aggregate_egress.enabled = True
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
    app = _app(settings)
    namespaced = function_name_for("demo", "ping")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        listed = await client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
        )
        assert listed.status_code == 200
        names = {t["name"] for t in listed.json()["result"]["tools"]}
        assert namespaced in names
        assert "route" in names
        # Coarse mcp_* stub omitted when aggregating.
        assert "mcp_demo" not in names

        called = await client.post(
            "/mcp",
            json={
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {"name": namespaced, "arguments": {}},
            },
        )
    assert called.status_code == 200, called.text
    result = called.json()["result"]
    assert result.get("isError") is not True
    text = json.dumps(result)
    assert "pong" in text
    assert any(b.get("method") == "tools/call" for b in seen)


@pytest.mark.asyncio
async def test_server_policy_omits_denied_server(settings, monkeypatch):
    settings.integrations.mcp_aggregate_egress.enabled = True
    settings.integrations.mcp_servers = [
        McpServerSettings(id="demo", url="http://mcp.test/rpc"),
        McpServerSettings(id="shell", url="http://mcp.shell.test/rpc"),
    ]
    settings.integrations.mcp_policy.servers.allow = ["demo"]

    def handler(request: httpx.Request) -> httpx.Response:
        host = request.url.host
        body = json.loads(request.content.decode())
        assert host == "mcp.test", host
        return httpx.Response(
            200,
            json={
                "jsonrpc": "2.0",
                "id": body.get("id", 1),
                "result": {
                    "tools": [
                        {
                            "name": "ping",
                            "description": "ping",
                            "inputSchema": {"type": "object", "properties": {}},
                        }
                    ]
                },
            },
        )

    monkeypatch.setattr(httpx, "AsyncClient", _patched_client(handler))
    app = _app(settings)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        listed = await client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
        )
        denied = await client.post(
            "/mcp",
            json={
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {"name": function_name_for("shell", "x"), "arguments": {}},
            },
        )
    names = {t["name"] for t in listed.json()["result"]["tools"]}
    assert function_name_for("demo", "ping") in names
    assert function_name_for("shell", "x") not in names
    assert denied.json()["error"]["code"] == TOOL_DENIED
    assert denied.json()["error"].get("data", {}).get("server") == "shell"


@pytest.mark.asyncio
async def test_tool_policy_filters_namespaced(settings, monkeypatch):
    settings.integrations.mcp_aggregate_egress.enabled = True
    settings.integrations.mcp_servers = [
        McpServerSettings(id="demo", url="http://mcp.test/rpc"),
    ]
    settings.integrations.mcp_policy.deny = ["demo__ping"]

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode())
        return httpx.Response(
            200,
            json={
                "jsonrpc": "2.0",
                "id": body.get("id", 1),
                "result": {
                    "tools": [
                        {
                            "name": "ping",
                            "description": "ping",
                            "inputSchema": {"type": "object", "properties": {}},
                        },
                        {
                            "name": "pong",
                            "description": "pong",
                            "inputSchema": {"type": "object", "properties": {}},
                        },
                    ]
                },
            },
        )

    monkeypatch.setattr(httpx, "AsyncClient", _patched_client(handler))
    app = _app(settings)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        listed = await client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
        )
    names = {t["name"] for t in listed.json()["result"]["tools"]}
    assert "demo__ping" not in names
    assert "demo__pong" in names


@pytest.mark.asyncio
async def test_list_failure_degrades_per_server(settings, monkeypatch):
    settings.integrations.mcp_aggregate_egress.enabled = True
    settings.integrations.mcp_servers = [
        McpServerSettings(id="bad", url="http://mcp.bad.test/rpc"),
        McpServerSettings(id="good", url="http://mcp.good.test/rpc"),
    ]
    events: list[tuple[str, dict]] = []

    def capture(event: str, payload: dict) -> None:
        events.append((event, payload))

    monkeypatch.setattr(
        "daari.gateway.mcp.log_gateway_event",
        capture,
    )

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode())
        if request.url.host == "mcp.bad.test":
            return httpx.Response(500, text="boom")
        return httpx.Response(
            200,
            json={
                "jsonrpc": "2.0",
                "id": body.get("id", 1),
                "result": {
                    "tools": [
                        {
                            "name": "ok",
                            "description": "ok",
                            "inputSchema": {"type": "object", "properties": {}},
                        }
                    ]
                },
            },
        )

    monkeypatch.setattr(httpx, "AsyncClient", _patched_client(handler))
    app = _app(settings)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        listed = await client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
        )
    assert listed.status_code == 200
    names = {t["name"] for t in listed.json()["result"]["tools"]}
    assert "good__ok" in names
    assert "route" in names
    assert any(e[0] == "mcp_aggregate_egress_list_failed" for e in events)
