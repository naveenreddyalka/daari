"""F5 MCP egress client (issue #121)."""

from __future__ import annotations

import json

import httpx
import pytest

from daari.config.settings import McpServerSettings
from daari.gateway.internal import InternalRequest, Message
from daari.providers.mcp_egress import McpEgressProvider, McpServerConfig, build_mcp_providers


@pytest.mark.asyncio
async def test_tools_list(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"jsonrpc": "2.0", "id": 1, "result": {"tools": [{"name": "ping"}]}}
        )

    class Patched(httpx.AsyncClient):
        def __init__(self, *args, **kwargs):
            kwargs["transport"] = httpx.MockTransport(handler)
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", Patched)
    provider = McpEgressProvider(
        McpServerConfig(id="demo", url="http://mcp.test/rpc", triggers=["@mcp:demo"])
    )
    result = await provider.execute(
        InternalRequest(
            messages=[Message(role="user", content="@mcp:demo tools/list")],
            model="daari",
        )
    )
    assert "ping" in result.content
    assert result.daari_meta.provider_id == "mcp:demo"


@pytest.mark.asyncio
async def test_outbound_requests_carry_mcp_method_and_name_headers(monkeypatch):
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": 1, "result": {"ok": True}})

    class Patched(httpx.AsyncClient):
        def __init__(self, *args, **kwargs):
            kwargs["transport"] = httpx.MockTransport(handler)
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", Patched)
    provider = McpEgressProvider(McpServerConfig(id="demo", url="http://mcp.test/rpc"))
    await provider.execute(
        InternalRequest(
            messages=[Message(role="user", content="@mcp:demo get_forecast Paris")],
            model="daari",
        )
    )
    await provider.execute(
        InternalRequest(messages=[Message(role="user", content="@mcp:demo tools/list")], model="daari")
    )
    call, listing = seen
    assert call.headers["Mcp-Method"] == "tools/call"
    assert call.headers["Mcp-Name"] == "get_forecast"
    assert listing.headers["Mcp-Method"] == "tools/list"
    assert "Mcp-Name" not in listing.headers


def _patched_client(handler):
    class Patched(httpx.AsyncClient):
        def __init__(self, *args, **kwargs):
            kwargs["transport"] = httpx.MockTransport(handler)
            super().__init__(*args, **kwargs)

    return Patched


@pytest.mark.asyncio
async def test_tools_list_follows_next_cursor_and_dedupes(monkeypatch):
    seen_cursors: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        cursor = (body.get("params") or {}).get("cursor")
        seen_cursors.append(cursor)
        if cursor is None:
            return httpx.Response(
                200,
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "result": {
                        "tools": [{"name": "alpha"}, {"name": "beta"}],
                        "nextCursor": "page-2",
                    },
                },
            )
        return httpx.Response(
            200,
            json={
                "jsonrpc": "2.0",
                "id": 2,
                "result": {
                    "tools": [{"name": "beta"}, {"name": "gamma"}],
                },
            },
        )

    monkeypatch.setattr(httpx, "AsyncClient", _patched_client(handler))
    provider = McpEgressProvider(McpServerConfig(id="demo", url="http://mcp.test/rpc"))
    result = await provider.execute(
        InternalRequest(
            messages=[Message(role="user", content="@mcp:demo tools/list")],
            model="daari",
        )
    )
    assert seen_cursors == [None, "page-2"]
    assert result.content.index("alpha") < result.content.index("beta") < result.content.index("gamma")
    assert result.content.count("beta") == 1


@pytest.mark.asyncio
async def test_tools_list_stops_on_page_cap_and_timeout(monkeypatch):
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(
            200,
            json={
                "jsonrpc": "2.0",
                "id": calls["n"],
                "result": {
                    "tools": [{"name": f"tool-{calls['n']}"}],
                    "nextCursor": "forever",
                },
            },
        )

    monkeypatch.setattr(httpx, "AsyncClient", _patched_client(handler))
    provider = McpEgressProvider(McpServerConfig(id="demo", url="http://mcp.test/rpc"))
    provider.list_page_cap = 3
    result = await provider.execute(
        InternalRequest(
            messages=[Message(role="user", content="@mcp:demo list")],
            model="daari",
        )
    )
    assert calls["n"] == 3
    assert "tool-1" in result.content and "tool-3" in result.content

    calls["n"] = 0
    provider.list_page_cap = 20
    provider.list_timeout_seconds = 0
    await provider.execute(
        InternalRequest(
            messages=[Message(role="user", content="@mcp:demo list")],
            model="daari",
        )
    )
    assert calls["n"] == 1


def test_build_from_settings():
    providers = build_mcp_providers(
        [McpServerSettings(id="corp", url="http://corp/mcp")]
    )
    assert len(providers) == 1
    assert providers[0].id == "mcp:corp"
    assert "@mcp:corp" in providers[0].server.triggers
