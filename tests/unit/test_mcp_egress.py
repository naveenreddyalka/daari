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


# --- semantic tool search (#376) --------------------------------------------


class _AxisEmbedder:
    """Deterministic fake: weather→[1,0], code→[0,1], other→[0.5,0.5]."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    async def embed(self, text: str, *, model: str | None = None):
        self.calls.append(text)
        lowered = text.lower()
        if "weather" in lowered or "forecast" in lowered:
            return [1.0, 0.0]
        if "code" in lowered or "repo" in lowered or "git" in lowered:
            return [0.0, 1.0]
        return [0.5, 0.5]


def _tools_catalog(n: int = 50) -> list[dict]:
    tools = []
    for index in range(n):
        if index == 0:
            tools.append(
                {"name": "get_forecast", "description": "weather forecast for a city"}
            )
        elif index == 1:
            tools.append({"name": "git_status", "description": "repo code status"})
        else:
            tools.append({"name": f"tool_{index}", "description": f"generic helper {index}"})
    return tools


@pytest.mark.asyncio
async def test_tool_search_threshold_gating_skips_embedder():
    from daari.gateway.mcp_policy import McpToolPolicy
    from daari.gateway.mcp_tool_search import ToolSearchSettings, maybe_rank_tools

    embedder = _AxisEmbedder()
    tools = _tools_catalog(10)
    settings = ToolSearchSettings(enabled=True, min_catalog_size=40, top_k=5)
    out = await maybe_rank_tools(
        tools, query="weather", settings=settings, embedder=embedder, server_id="demo"
    )
    assert out == tools
    assert embedder.calls == []

    off = await maybe_rank_tools(
        _tools_catalog(50),
        query="weather",
        settings=ToolSearchSettings(enabled=False, min_catalog_size=10, top_k=5),
        embedder=embedder,
        server_id="demo",
    )
    assert len(off) == 50
    assert embedder.calls == []


@pytest.mark.asyncio
async def test_tool_search_top_k_orders_by_similarity():
    from daari.gateway.mcp_tool_search import ToolSearchSettings, maybe_rank_tools

    embedder = _AxisEmbedder()
    tools = _tools_catalog(50)
    settings = ToolSearchSettings(enabled=True, min_catalog_size=40, top_k=3)
    out = await maybe_rank_tools(
        tools, query="weather forecast", settings=settings, embedder=embedder, server_id="demo"
    )
    assert len(out) == 3
    assert out[0]["name"] == "get_forecast"


@pytest.mark.asyncio
async def test_tool_search_governance_filters_before_ranking():
    from daari.gateway.mcp_policy import McpToolPolicy
    from daari.gateway.mcp_tool_search import ToolSearchSettings, maybe_rank_tools

    embedder = _AxisEmbedder()
    tools = _tools_catalog(50)
    tools.append({"name": "secret_weather", "description": "weather for admins only"})
    policy = McpToolPolicy(deny=("secret_*",))
    settings = ToolSearchSettings(enabled=True, min_catalog_size=40, top_k=5)
    out = await maybe_rank_tools(
        tools,
        query="weather",
        settings=settings,
        policy=policy,
        embedder=embedder,
        server_id="demo",
    )
    names = [t["name"] for t in out]
    assert "secret_weather" not in names
    assert "get_forecast" in names


@pytest.mark.asyncio
async def test_tool_search_degrades_when_embedder_fails(monkeypatch):
    from daari.gateway.mcp_tool_search import ToolSearchSettings, maybe_rank_tools

    events: list[tuple[str, dict]] = []
    monkeypatch.setattr(
        "daari.gateway.request_log.log_gateway_event",
        lambda event, payload: events.append((event, payload)),
    )

    class Boom:
        async def embed(self, text: str, *, model: str | None = None):
            return None

    tools = _tools_catalog(50)
    out = await maybe_rank_tools(
        tools,
        query="weather",
        settings=ToolSearchSettings(enabled=True, min_catalog_size=10, top_k=5),
        embedder=Boom(),
        server_id="demo",
    )
    assert len(out) == 50
    assert any(event == "mcp_tool_search_degraded" for event, _ in events)


@pytest.mark.asyncio
async def test_tool_search_caches_embeddings_across_lists():
    from daari.gateway.mcp_tool_search import (
        ToolEmbeddingCache,
        ToolSearchSettings,
        maybe_rank_tools,
    )

    embedder = _AxisEmbedder()
    cache = ToolEmbeddingCache()
    tools = _tools_catalog(50)
    settings = ToolSearchSettings(enabled=True, min_catalog_size=10, top_k=5)
    await maybe_rank_tools(
        tools,
        query="weather",
        settings=settings,
        embedder=embedder,
        server_id="demo",
        cache=cache,
    )
    first_calls = len(embedder.calls)
    await maybe_rank_tools(
        tools,
        query="weather",
        settings=settings,
        embedder=embedder,
        server_id="demo",
        cache=cache,
    )
    # Second pass embeds the query again but not unchanged tool documents.
    assert len(embedder.calls) == first_calls + 1


@pytest.mark.asyncio
async def test_egress_list_applies_tool_search(monkeypatch):
    tools = _tools_catalog(50)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"jsonrpc": "2.0", "id": 1, "result": {"tools": tools}}
        )

    monkeypatch.setattr(httpx, "AsyncClient", _patched_client(handler))
    from daari.gateway.mcp_tool_search import ToolSearchSettings

    provider = McpEgressProvider(
        McpServerConfig(id="demo", url="http://mcp.test/rpc"),
        tool_search=ToolSearchSettings(enabled=True, min_catalog_size=40, top_k=3),
        embedder=_AxisEmbedder(),
    )
    result = await provider.execute(
        InternalRequest(
            messages=[Message(role="user", content="@mcp:demo tools/list weather")],
            model="daari",
        )
    )
    assert "get_forecast" in result.content
    # top_k=3 — most generic tools should be absent from the truncated catalog string
    assert "tool_40" not in result.content
