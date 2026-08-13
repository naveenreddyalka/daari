"""JSON-RPC 2.0 MCP server at POST /mcp (issue #162)."""

from __future__ import annotations

import json

import pytest
from httpx import ASGITransport, AsyncClient

from daari.gateway.internal import DaariMeta, InternalRequest, InternalResponse
from daari.providers.integrations import HttpIntegrationProvider
from daari.router.router import AppContext
from daari.server.app import create_app
from tests.conftest import META_HEADERS, mock_all_ollama_executors


def _app(settings):
    application = create_app(settings)
    application.state.ctx = AppContext.from_settings(settings)
    return application


async def _rpc(client: AsyncClient, method: str, params: dict | None = None, *, rpc_id: int = 1, **kwargs):
    body: dict = {"jsonrpc": "2.0", "id": rpc_id, "method": method}
    if params is not None:
        body["params"] = params
    return await client.post("/mcp", json=body, headers=META_HEADERS, **kwargs)


@pytest.mark.asyncio
async def test_initialize_handshake(settings):
    transport = ASGITransport(app=_app(settings))
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await _rpc(
            client,
            "initialize",
            {
                "protocolVersion": "2025-03-26",
                "capabilities": {},
                "clientInfo": {"name": "test", "version": "0"},
            },
        )
    assert response.status_code == 200
    payload = response.json()
    assert payload["jsonrpc"] == "2.0"
    assert payload["id"] == 1
    result = payload["result"]
    assert result["protocolVersion"] == "2025-03-26"
    assert "tools" in result["capabilities"]
    assert result["serverInfo"]["name"] == "daari"


@pytest.mark.asyncio
async def test_initialized_notification_is_accepted(settings):
    transport = ASGITransport(app=_app(settings))
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "method": "notifications/initialized"},
            headers=META_HEADERS,
        )
    assert response.status_code == 202
    assert response.content == b""


@pytest.mark.asyncio
async def test_tools_list_exposes_route_and_stats_with_input_schema(settings):
    transport = ASGITransport(app=_app(settings))
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await _rpc(client, "tools/list")
    assert response.status_code == 200
    tools = {tool["name"]: tool for tool in response.json()["result"]["tools"]}
    assert "route" in tools
    assert "stats" in tools
    assert tools["route"]["inputSchema"]["type"] == "object"
    assert "input" in tools["route"]["inputSchema"]["properties"]
    assert tools["stats"]["inputSchema"]["type"] == "object"


@pytest.mark.asyncio
async def test_tools_call_route_returns_mcp_content(settings, monkeypatch):
    app = _app(settings)

    async def fake_execute(_request: InternalRequest) -> InternalResponse:
        return InternalResponse(
            content="from-mcp",
            model="llama3.2:3b",
            daari_meta=DaariMeta(tier="L3", executor="ollama", provider_id="ollama:l3"),
        )

    mock_all_ollama_executors(monkeypatch, app.state.ctx.router, fake_execute)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await _rpc(
            client,
            "tools/call",
            {"name": "route", "arguments": {"input": "hello"}},
        )
    assert response.status_code == 200
    result = response.json()["result"]
    assert result["content"][0]["type"] == "text"
    assert result["content"][0]["text"] == "from-mcp"
    assert result.get("isError") is not True


@pytest.mark.asyncio
async def test_unknown_method_is_jsonrpc_method_not_found(settings):
    transport = ASGITransport(app=_app(settings))
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await _rpc(client, "prompts/get")
    assert response.status_code == 200
    error = response.json()["error"]
    assert error["code"] == -32601


@pytest.mark.asyncio
async def test_invalid_json_is_parse_error(settings):
    transport = ASGITransport(app=_app(settings))
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/mcp",
            content=b"{not-json",
            headers={**META_HEADERS, "content-type": "application/json"},
        )
    assert response.status_code == 400
    payload = response.json()
    assert payload["error"]["code"] == -32700
    assert payload["id"] is None


@pytest.mark.asyncio
async def test_legacy_query_is_deprecated_alias(settings, monkeypatch):
    app = _app(settings)

    async def fake_execute(_request: InternalRequest) -> InternalResponse:
        return InternalResponse(
            content="legacy",
            model="llama3.2:3b",
            daari_meta=DaariMeta(tier="L3", executor="ollama", provider_id="ollama:l3"),
        )

    mock_all_ollama_executors(monkeypatch, app.state.ctx.router, fake_execute)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/v1/mcp/query",
            json={"tool": "route", "input": "hello"},
            headers=META_HEADERS,
        )
    assert response.status_code == 200
    assert response.json()["result"]["content"] == "legacy"
    assert response.headers.get("deprecation", "").lower() in {"true", "1"}
    assert "/mcp" in (response.headers.get("link") or "")


@pytest.mark.asyncio
async def test_mcp_requires_existing_api_key_auth(settings):
    settings.server.api_key = "sekret-key"
    transport = ASGITransport(app=_app(settings))
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        denied = await client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
        )
        allowed = await client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
            headers={"Authorization": "Bearer sekret-key"},
        )
    assert denied.status_code == 401
    assert allowed.status_code == 200
    assert allowed.json()["result"]["tools"]


@pytest.mark.asyncio
async def test_configured_provider_is_listed_and_callable(settings):
    app = _app(settings)

    class FakeSourcegraph(HttpIntegrationProvider):
        def __init__(self) -> None:
            super().__init__(id="integration:sourcegraph", base_url="http://sg.test")

        async def execute(self, request: InternalRequest) -> InternalResponse:
            return InternalResponse(
                content="sg-hit",
                model=request.model,
                daari_meta=DaariMeta(tier="Lt", executor="integration", provider_id=self.id),
            )

    app.state.ctx.providers.register(FakeSourcegraph())
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        listed = await _rpc(client, "tools/list")
        called = await _rpc(
            client,
            "tools/call",
            {"name": "sourcegraph", "arguments": {"input": "repo:daari"}},
        )
    names = {tool["name"] for tool in listed.json()["result"]["tools"]}
    assert "sourcegraph" in names
    assert called.json()["result"]["content"][0]["text"] == "sg-hit"


@pytest.mark.asyncio
async def test_streamable_http_can_return_sse(settings):
    transport = ASGITransport(app=_app(settings))
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "id": 7, "method": "tools/list"},
            headers={
                **META_HEADERS,
                "accept": "text/event-stream",
            },
        )
    assert response.status_code == 200
    assert "text/event-stream" in response.headers["content-type"]
    assert "data:" in response.text
    data_line = next(line for line in response.text.splitlines() if line.startswith("data:"))
    payload = json.loads(data_line[len("data:") :].strip())
    assert payload["id"] == 7
    assert payload["result"]["tools"]
