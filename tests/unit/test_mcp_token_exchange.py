"""RFC 8693 OBO token exchange for egress mcp_servers (#1319)."""

from __future__ import annotations

import json
import socket
from pathlib import Path
from urllib.parse import parse_qs

import httpx
import pytest
from httpx import ASGITransport, AsyncClient

from daari.config.settings import McpServerSettings
from daari.gateway.internal import InternalRequest, Message, RequestMeta
from daari.providers.mcp_egress import McpEgressProvider, McpServerConfig, build_mcp_providers
from daari.router.router import AppContext
from daari.server.app import create_app
from daari.setup.doctor import _check_mcp_token_exchange, run_doctor


@pytest.fixture(autouse=True)
def _public_dns_for_fake_hosts(monkeypatch):
    def fake_getaddrinfo(host, port, *args, **kwargs):
        return [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port or 0))
        ]

    monkeypatch.setattr("daari.security.egress_url.socket.getaddrinfo", fake_getaddrinfo)


def _obo_server(**overrides) -> McpServerConfig:
    base = dict(
        id="corp",
        url="http://mcp.corp.test/rpc",
        auth_type="oauth2_token_exchange",
        token_exchange_endpoint="http://idp.corp.test/oauth/token",
        client_id="daari-mcp",
        client_secret="super-secret",
        audience="mcp-api",
        scopes=["mcp.read", "mcp.call"],
    )
    base.update(overrides)
    return McpServerConfig(**base)


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


@pytest.mark.asyncio
async def test_exchange_then_egress_uses_exchanged_token(monkeypatch):
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        host = request.url.host
        if host == "idp.corp.test":
            form = parse_qs(request.content.decode())
            assert form["grant_type"] == ["urn:ietf:params:oauth:grant-type:token-exchange"]
            assert form["subject_token"] == ["inbound-jwt"]
            assert form["subject_token_type"] == [
                "urn:ietf:params:oauth:token-type:access_token"
            ]
            assert form["client_id"] == ["daari-mcp"]
            assert form["client_secret"] == ["super-secret"]
            assert form["audience"] == ["mcp-api"]
            assert form["scope"] == ["mcp.read mcp.call"]
            return httpx.Response(
                200,
                json={
                    "access_token": "upstream-mcp-token",
                    "token_type": "Bearer",
                    "expires_in": 3600,
                },
            )
        assert host == "mcp.corp.test"
        assert request.headers["Authorization"] == "Bearer upstream-mcp-token"
        body = json.loads(request.content.decode())
        assert body["method"] == "tools/call"
        return httpx.Response(
            200,
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "result": {"content": [{"type": "text", "text": "ok"}]},
            },
        )

    monkeypatch.setattr(httpx, "AsyncClient", _patched_client(handler))
    provider = McpEgressProvider(_obo_server())
    result = await provider.call_tool(
        InternalRequest(
            messages=[Message(role="user", content="")],
            model="daari",
            meta=RequestMeta(authorization_bearer="inbound-jwt"),
        ),
        tool="ping",
        arguments={},
    )
    assert result.daari_meta.warning is None
    assert "ok" in result.content
    assert len(seen) == 2
    assert seen[0].url.host == "idp.corp.test"
    assert seen[1].url.host == "mcp.corp.test"
    # Never forward the inbound subject token upstream.
    assert seen[1].headers["Authorization"] != "Bearer inbound-jwt"


@pytest.mark.asyncio
async def test_exchange_cache_reuses_token_until_expiry(monkeypatch):
    exchanges = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal exchanges
        if request.url.host == "idp.corp.test":
            exchanges += 1
            return httpx.Response(
                200,
                json={"access_token": "cached-tok", "expires_in": 3600},
            )
        return httpx.Response(
            200,
            json={"jsonrpc": "2.0", "id": 1, "result": {"tools": [{"name": "ping"}]}},
        )

    monkeypatch.setattr(httpx, "AsyncClient", _patched_client(handler))
    provider = McpEgressProvider(_obo_server())
    req = InternalRequest(
        messages=[Message(role="user", content="")],
        model="daari",
        meta=RequestMeta(authorization_bearer="same-subject"),
    )
    first, err1 = await provider.list_tools_catalog(req)
    second, err2 = await provider.list_tools_catalog(req)
    assert err1 is None and err2 is None
    assert first and second
    assert exchanges == 1


@pytest.mark.asyncio
async def test_missing_subject_token_fails_closed(monkeypatch):
    called = False

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal called
        called = True
        return httpx.Response(500)

    monkeypatch.setattr(httpx, "AsyncClient", _patched_client(handler))
    provider = McpEgressProvider(_obo_server())
    result = await provider.call_tool(
        InternalRequest(
            messages=[Message(role="user", content="")],
            model="daari",
        ),
        tool="ping",
    )
    assert result.daari_meta.warning == "mcp_token_exchange_missing_subject"
    assert called is False


@pytest.mark.asyncio
async def test_exchange_http_error_fails_closed(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "idp.corp.test":
            return httpx.Response(400, json={"error": "invalid_grant"})
        return httpx.Response(500)

    monkeypatch.setattr(httpx, "AsyncClient", _patched_client(handler))
    provider = McpEgressProvider(_obo_server())
    result = await provider.call_tool(
        InternalRequest(
            messages=[Message(role="user", content="")],
            model="daari",
            meta=RequestMeta(authorization_bearer="inbound-jwt"),
        ),
        tool="ping",
    )
    assert result.daari_meta.warning == "mcp_token_exchange_failed"


@pytest.mark.asyncio
async def test_ssrf_blocked_exchange_endpoint_fails_closed(monkeypatch):
    def fake_getaddrinfo(host, port, *args, **kwargs):
        if host == "meta.local":
            return [
                (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("169.254.169.254", port or 0))
            ]
        return [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port or 0))
        ]

    monkeypatch.setattr("daari.security.egress_url.socket.getaddrinfo", fake_getaddrinfo)
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return httpx.Response(500)

    monkeypatch.setattr(httpx, "AsyncClient", _patched_client(handler))
    provider = McpEgressProvider(
        _obo_server(token_exchange_endpoint="http://meta.local/latest/token")
    )
    result = await provider.call_tool(
        InternalRequest(
            messages=[Message(role="user", content="")],
            model="daari",
            meta=RequestMeta(authorization_bearer="inbound-jwt"),
        ),
        tool="ping",
    )
    assert result.daari_meta.warning == "mcp_token_exchange_ssrf"
    assert seen == []


@pytest.mark.asyncio
async def test_asgi_tools_call_missing_subject_returns_401(settings, monkeypatch):
    settings.integrations.mcp_aggregate_egress.enabled = True
    settings.integrations.mcp_servers = [
        McpServerSettings(
            id="corp",
            url="http://mcp.corp.test/rpc",
            auth_type="oauth2_token_exchange",
            token_exchange_endpoint="http://idp.corp.test/oauth/token",
            client_id="daari-mcp",
            client_secret="super-secret",
        )
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "should not be called"})

    monkeypatch.setattr(httpx, "AsyncClient", _patched_client(handler))
    app = _app(settings)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/mcp",
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": "corp__ping", "arguments": {}},
            },
        )
    assert response.status_code == 401
    body = response.json()
    assert "error" in body


@pytest.mark.asyncio
async def test_asgi_tools_call_exchange_then_egress(settings, monkeypatch):
    settings.integrations.mcp_aggregate_egress.enabled = True
    settings.integrations.mcp_servers = [
        McpServerSettings(
            id="corp",
            url="http://mcp.corp.test/rpc",
            auth_type="oauth2_token_exchange",
            token_exchange_endpoint="http://idp.corp.test/oauth/token",
            client_id="daari-mcp",
            client_secret="super-secret",
        )
    ]
    seen_auth: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "idp.corp.test":
            return httpx.Response(
                200,
                json={"access_token": "up-tok", "expires_in": 600},
            )
        seen_auth.append(request.headers.get("Authorization", ""))
        body = json.loads(request.content.decode())
        if body.get("method") == "tools/list":
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
    headers = {"Authorization": "Bearer inbound-subject"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        listed = await client.post(
            "/mcp",
            headers=headers,
            json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
        )
        assert listed.status_code == 200
        names = {t["name"] for t in listed.json()["result"]["tools"]}
        assert "corp__ping" in names
        called = await client.post(
            "/mcp",
            headers=headers,
            json={
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {"name": "corp__ping", "arguments": {}},
            },
        )
    assert called.status_code == 200
    assert "pong" in json.dumps(called.json())
    assert all(a == "Bearer up-tok" for a in seen_auth)


def test_build_mcp_providers_copies_auth_fields():
    providers = build_mcp_providers(
        [
            McpServerSettings(
                id="corp",
                url="http://mcp.corp.test/rpc",
                auth_type="oauth2_token_exchange",
                token_exchange_endpoint="http://idp.corp.test/token",
                client_id="cid",
                client_secret="csec",
                audience="aud",
                scopes=["a", "b"],
                subject_token_type="access_token",
            )
        ]
    )
    assert len(providers) == 1
    cfg = providers[0].server
    assert cfg.auth_type == "oauth2_token_exchange"
    assert cfg.token_exchange_endpoint == "http://idp.corp.test/token"
    assert cfg.client_id == "cid"
    assert cfg.client_secret == "csec"
    assert cfg.audience == "aud"
    assert cfg.scopes == ["a", "b"]


def test_doctor_tip_when_any_server_uses_token_exchange(settings):
    settings.integrations.mcp_servers = [
        McpServerSettings(
            id="corp",
            url="http://mcp.corp.test/rpc",
            auth_type="oauth2_token_exchange",
            token_exchange_endpoint="http://idp.corp.test/token",
            client_id="cid",
            client_secret="csec",
        )
    ]
    row = _check_mcp_token_exchange(settings)
    assert row is not None
    assert row.name == "mcp_token_exchange"
    assert row.optional is True
    assert row.ok is True
    detail = row.detail.lower()
    assert "token" in detail and "exchange" in detail


def test_doctor_tip_absent_without_token_exchange(settings):
    settings.integrations.mcp_servers = [
        McpServerSettings(id="demo", url="http://mcp.test/rpc", token="static"),
    ]
    assert _check_mcp_token_exchange(settings) is None
    rows = run_doctor(settings, httpx_client=None)
    assert not any(r.name == "mcp_token_exchange" for r in rows)


def test_docs_mention_token_exchange_knobs():
    mcp = Path("docs/developer/guides/clients/mcp.md").read_text()
    assert "oauth2_token_exchange" in mcp
    assert "token_exchange_endpoint" in mcp
    config = Path("docs/developer/reference/config.md").read_text()
    assert "oauth2_token_exchange" in config or "token_exchange_endpoint" in config
    doctor = Path("docs/developer/guides/operations/doctor-health.md").read_text()
    assert "mcp_token_exchange" in doctor
