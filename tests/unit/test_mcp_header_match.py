"""Reject Mcp-Method / Mcp-Name mismatches vs JSON-RPC body (#1233)."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from daari.gateway.mcp import HEADER_MISMATCH
from daari.router.router import AppContext
from daari.server.app import create_app
from tests.conftest import META_HEADERS


def _app(settings):
    application = create_app(settings)
    application.state.ctx = AppContext.from_settings(settings)
    return application


async def _rpc(
    client: AsyncClient,
    method: str,
    params: dict | None = None,
    *,
    headers: dict | None = None,
    rpc_id: int = 1,
):
    body: dict = {"jsonrpc": "2.0", "id": rpc_id, "method": method}
    if params is not None:
        body["params"] = params
    return await client.post(
        "/mcp", json=body, headers={**META_HEADERS, **(headers or {})}
    )


@pytest.mark.asyncio
async def test_matching_mcp_headers_pass(settings):
    transport = ASGITransport(app=_app(settings))
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await _rpc(
            client,
            "tools/call",
            {"name": "health", "arguments": {}},
            headers={"Mcp-Method": "tools/call", "Mcp-Name": "health"},
        )
    assert response.status_code == 200
    assert "result" in response.json()


@pytest.mark.asyncio
async def test_absent_mcp_headers_still_allowed(settings):
    transport = ASGITransport(app=_app(settings))
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await _rpc(client, "tools/list", {})
    assert response.status_code == 200
    assert "tools" in response.json()["result"]


@pytest.mark.asyncio
async def test_mcp_method_mismatch_returns_400(settings):
    transport = ASGITransport(app=_app(settings))
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await _rpc(
            client,
            "tools/list",
            {},
            headers={"Mcp-Method": "tools/call"},
        )
    assert response.status_code == 400
    err = response.json()["error"]
    assert err["code"] == HEADER_MISMATCH
    assert "Mcp-Method" in err["message"] or "mcp-method" in err["message"].lower()
    assert err["data"]["header"] == "Mcp-Method"
    assert err["data"]["header_value"] == "tools/call"
    assert err["data"]["body_value"] == "tools/list"


@pytest.mark.asyncio
async def test_mcp_name_mismatch_on_tools_call_returns_400(settings):
    transport = ASGITransport(app=_app(settings))
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await _rpc(
            client,
            "tools/call",
            {"name": "health", "arguments": {}},
            headers={"Mcp-Method": "tools/call", "Mcp-Name": "stats"},
        )
    assert response.status_code == 400
    err = response.json()["error"]
    assert err["code"] == HEADER_MISMATCH
    assert "Mcp-Name" in err["message"] or "mcp-name" in err["message"].lower()
    assert err["data"]["header"] == "Mcp-Name"
    assert err["data"]["header_value"] == "stats"
    assert err["data"]["body_value"] == "health"
