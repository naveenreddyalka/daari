"""SEP-3415 Events Extension relay through /mcp (#2368)."""

from __future__ import annotations

import json
import socket

import httpx
import pytest
from httpx import ASGITransport, AsyncClient

from daari.auth.virtual_keys import VirtualKeyStore
from daari.config.settings import McpServerSettings
from daari.gateway.mcp import INTERNAL_ERROR, METHOD_NOT_FOUND
from daari.gateway.mcp_tasks import EVENTS_EXTENSION, SKILLS_EXTENSION, initialize_capabilities
from daari.router.router import AppContext
from daari.server.app import create_app
from tests.conftest import META_HEADERS


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


async def _rpc(client: AsyncClient, method: str, params: dict | None = None, *, rpc_id: int = 1):
    body: dict = {"jsonrpc": "2.0", "id": rpc_id, "method": method}
    if params is not None:
        body["params"] = params
    return await client.post("/mcp", json=body, headers=META_HEADERS)


def _events_upstream(
    *,
    list_changed: bool = False,
    list_result: dict | None = None,
    poll_result: dict | None = None,
):
    """MockTransport handler that speaks initialize + events/list + events/poll."""

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode())
        method = body.get("method")
        rpc_id = body.get("id", 1)
        if method == "initialize":
            return httpx.Response(
                200,
                json={
                    "jsonrpc": "2.0",
                    "id": rpc_id,
                    "result": {
                        "protocolVersion": "2026-07-28",
                        "capabilities": {
                            "extensions": {
                                EVENTS_EXTENSION: {"listChanged": list_changed},
                            }
                        },
                        "serverInfo": {"name": "upstream-events", "version": "0"},
                    },
                },
            )
        if method == "events/list":
            result = list_result or {
                "resultType": "complete",
                "events": [
                    {
                        "name": "email.received",
                        "delivery": ["poll"],
                        "inputSchema": {"type": "object"},
                        "payloadSchema": {"type": "object"},
                    }
                ],
                "nextCursor": body.get("params", {}).get("cursor"),
            }
            return httpx.Response(
                200, json={"jsonrpc": "2.0", "id": rpc_id, "result": result}
            )
        if method == "events/poll":
            result = poll_result or {
                "resultType": "complete",
                "events": [],
                "cursor": body.get("params", {}).get("cursor") or "opaque-cursor-1",
                "hasMore": False,
                "nextPollMs": 5000,
            }
            return httpx.Response(
                200, json={"jsonrpc": "2.0", "id": rpc_id, "result": result}
            )
        return httpx.Response(
            200,
            json={
                "jsonrpc": "2.0",
                "id": rpc_id,
                "error": {"code": -32601, "message": f"unknown {method}"},
            },
        )

    return handler


def test_capabilities_omit_events_without_upstream_extensions():
    caps = initialize_capabilities("2026-07-28")
    assert EVENTS_EXTENSION not in caps.get("extensions", {})
    assert SKILLS_EXTENSION in caps["extensions"]

    with_events = initialize_capabilities(
        "2026-07-28",
        upstream_extensions={EVENTS_EXTENSION: {"listChanged": True}},
    )
    assert with_events["extensions"][EVENTS_EXTENSION] == {"listChanged": True}
    assert SKILLS_EXTENSION in with_events["extensions"]


@pytest.mark.asyncio
async def test_initialize_advertises_events_only_when_egress_has_extension(
    settings, monkeypatch
):
    settings.integrations.mcp_servers = [
        McpServerSettings(id="demo", url="http://mcp.test/rpc"),
    ]
    monkeypatch.setattr(httpx, "AsyncClient", _patched_client(_events_upstream(list_changed=True)))
    app = _app(settings)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        init = await _rpc(
            client,
            "initialize",
            {
                "protocolVersion": "2026-07-28",
                "capabilities": {},
                "clientInfo": {"name": "test", "version": "0"},
            },
        )
    caps = init.json()["result"]["capabilities"]
    assert caps["extensions"][EVENTS_EXTENSION] == {"listChanged": True}
    assert SKILLS_EXTENSION in caps["extensions"]


@pytest.mark.asyncio
async def test_initialize_omits_events_when_egress_lacks_extension(settings, monkeypatch):
    settings.integrations.mcp_servers = [
        McpServerSettings(id="demo", url="http://mcp.test/rpc"),
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode())
        return httpx.Response(
            200,
            json={
                "jsonrpc": "2.0",
                "id": body.get("id", 1),
                "result": {
                    "protocolVersion": "2026-07-28",
                    "capabilities": {"tools": {"listChanged": False}},
                    "serverInfo": {"name": "plain", "version": "0"},
                },
            },
        )

    monkeypatch.setattr(httpx, "AsyncClient", _patched_client(handler))
    app = _app(settings)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        init = await _rpc(
            client,
            "initialize",
            {
                "protocolVersion": "2026-07-28",
                "capabilities": {},
                "clientInfo": {"name": "test", "version": "0"},
            },
        )
    caps = init.json()["result"]["capabilities"]
    assert EVENTS_EXTENSION not in caps.get("extensions", {})
    assert SKILLS_EXTENSION in caps["extensions"]


@pytest.mark.asyncio
async def test_events_list_and_poll_relay_with_opaque_cursors(settings, monkeypatch):
    settings.integrations.mcp_servers = [
        McpServerSettings(id="demo", url="http://mcp.test/rpc"),
    ]
    seen: list[dict] = []
    audit: list[tuple[str, dict]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode())
        seen.append(body)
        return _events_upstream()(request)

    monkeypatch.setattr(httpx, "AsyncClient", _patched_client(handler))
    monkeypatch.setattr(
        "daari.gateway.mcp.log_gateway_event",
        lambda event, payload: audit.append((event, payload)),
    )
    app = _app(settings)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await _rpc(
            client,
            "initialize",
            {
                "protocolVersion": "2026-07-28",
                "capabilities": {},
                "clientInfo": {"name": "test", "version": "0"},
            },
        )
        listed = await _rpc(
            client, "events/list", {"cursor": "page-token-a"}, rpc_id=2
        )
        polled = await _rpc(
            client,
            "events/poll",
            {
                "name": "email.received",
                "arguments": {"from": "*@example.com"},
                "cursor": "opaque-from-client",
            },
            rpc_id=3,
        )

    assert listed.status_code == 200
    assert listed.json()["result"]["events"][0]["name"] == "email.received"
    assert listed.json()["result"]["nextCursor"] == "page-token-a"

    assert polled.status_code == 200
    assert polled.json()["result"]["cursor"] == "opaque-from-client"

    list_calls = [b for b in seen if b.get("method") == "events/list"]
    poll_calls = [b for b in seen if b.get("method") == "events/poll"]
    assert list_calls[0]["params"]["cursor"] == "page-token-a"
    assert poll_calls[0]["params"]["cursor"] == "opaque-from-client"
    assert poll_calls[0]["params"]["name"] == "email.received"

    names = {e[0] for e in audit}
    assert "mcp_events_list" in names
    assert "mcp_events_poll" in names


@pytest.mark.asyncio
async def test_events_list_fail_closed_without_mcp_grant(settings):
    settings.integrations.mcp_policy.require_key_access_defined = True
    store = VirtualKeyStore(settings.virtual_keys_path)
    created = store.create("agent", client_id="agent", metadata={})
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    app.state.virtual_key_store = store
    app.state.ctx.virtual_key_store = store
    headers = {**META_HEADERS, "Authorization": f"Bearer {created.plaintext}"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        listed = await client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "id": 1, "method": "events/list"},
            headers=headers,
        )
    assert listed.json()["result"]["events"] == []


@pytest.mark.asyncio
async def test_events_stream_and_subscribe_not_supported(settings):
    app = _app(settings)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        stream = await _rpc(client, "events/stream", {"name": "email.received"})
        subscribe = await _rpc(
            client,
            "events/subscribe",
            {"name": "email.received", "callbackUrl": "https://example.com/hook"},
            rpc_id=2,
        )
    for response in (stream, subscribe):
        err = response.json()["error"]
        assert err["code"] == INTERNAL_ERROR
        assert "not supported" in err["message"].lower()


@pytest.mark.asyncio
async def test_unknown_events_method_returns_method_not_found(settings):
    app = _app(settings)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await _rpc(client, "events/explode")
    assert response.json()["error"]["code"] == METHOD_NOT_FOUND
