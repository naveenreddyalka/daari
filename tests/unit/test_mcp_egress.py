"""F5 MCP egress client (issue #121)."""

from __future__ import annotations

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


def test_build_from_settings():
    providers = build_mcp_providers(
        [McpServerSettings(id="corp", url="http://corp/mcp")]
    )
    assert len(providers) == 1
    assert providers[0].id == "mcp:corp"
    assert "@mcp:corp" in providers[0].server.triggers
