"""MCP egress Authorization must re-resolve secret:// tokens near use (#2281)."""

from __future__ import annotations

import json
import socket

import httpx
import pytest

from daari.gateway.internal import InternalRequest, Message
from daari.providers.mcp_egress import McpEgressProvider, McpServerConfig
from daari.security import secret_refs
from daari.security.secret_refs import (
    RefreshableSecret,
    clear_registered_secrets,
    resolve_secret_ref,
)

TOKEN_URL = "https://idp.example.com/oauth/token"
CLIENT_SECRET = "s3cr3t-client-value"
MCP_HOST = "mcp.test"


@pytest.fixture(autouse=True)
def _fresh_registry():
    clear_registered_secrets()
    yield
    clear_registered_secrets()


@pytest.fixture(autouse=True)
def _public_dns_for_fake_mcp_hosts(monkeypatch):
    def fake_getaddrinfo(host, port, *args, **kwargs):
        return [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port or 0))
        ]

    monkeypatch.setattr("daari.security.egress_url.socket.getaddrinfo", fake_getaddrinfo)


class FakeClock:
    def __init__(self, start: float = 1_000_000.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class TokenServer:
    def __init__(self, *, expires_in: int | None = 300, status: int = 200) -> None:
        self.expires_in = expires_in
        self.status = status
        self.requests: list[httpx.Request] = []
        self.issued = 0

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.status != 200:
            return httpx.Response(self.status, json={"error": "server_error"})
        self.issued += 1
        payload = {
            "access_token": f"tok-{self.issued}",
            "token_type": "Bearer",
        }
        if self.expires_in is not None:
            payload["expires_in"] = self.expires_in
        return httpx.Response(200, json=payload)

    @property
    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handler)


def _oauth_ref(secret_env: str) -> str:
    return (
        f"secret://oauth/{TOKEN_URL}"
        f"?client_id=daari-svc&client_secret={secret_env}"
    )


@pytest.fixture
def secret_env(tmp_path):
    env = tmp_path / "idp.env"
    env.write_text(f"IDP_SECRET={CLIENT_SECRET}\n", encoding="utf-8")
    return f"secret://env-file/{env}#IDP_SECRET"


def _mcp_ok(request: httpx.Request) -> httpx.Response:
    body = json.loads(request.content.decode())
    method = body.get("method")
    if method == "tools/list":
        return httpx.Response(
            200,
            json={"jsonrpc": "2.0", "id": 1, "result": {"tools": [{"name": "ping"}]}},
        )
    return httpx.Response(
        200,
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "result": {"content": [{"type": "text", "text": "ok"}]},
        },
    )


@pytest.mark.asyncio
async def test_egress_remints_expired_oauth_bearer(monkeypatch, secret_env):
    """After expiry, tools/call must send the re-minted Bearer, not boot tok (#2281)."""
    token_server = TokenServer(expires_in=300)
    clock = FakeClock()
    monkeypatch.setattr(secret_refs, "_default_transport", token_server.transport)
    monkeypatch.setattr(secret_refs, "_now", clock)

    ref = _oauth_ref(secret_env)
    boot = resolve_secret_ref(ref)
    assert boot == "tok-1" and isinstance(boot, RefreshableSecret)

    mcp_seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "idp.example.com":
            return token_server.handler(request)
        mcp_seen.append(request)
        assert request.url.host == MCP_HOST
        return _mcp_ok(request)

    class Patched(httpx.AsyncClient):
        def __init__(self, *args, **kwargs):
            kwargs["transport"] = httpx.MockTransport(handler)
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", Patched)

    events: list[tuple[str, dict]] = []

    def capture(name: str, payload: dict | None = None, **kwargs) -> None:
        events.append((name, dict(payload or {})))

    monkeypatch.setattr(
        "daari.gateway.request_log.log_gateway_event",
        capture,
    )

    provider = McpEgressProvider(
        McpServerConfig(
            id="demo",
            url=f"http://{MCP_HOST}/rpc",
            token=boot,
            triggers=["@mcp:demo"],
        )
    )
    req = InternalRequest(
        messages=[Message(role="user", content="@mcp:demo ping")],
        model="daari",
    )
    first = await provider.execute(req)
    assert first.daari_meta.warning is None
    assert mcp_seen[0].headers["Authorization"] == "Bearer tok-1"

    clock.advance(250)
    second = await provider.execute(req)
    assert second.daari_meta.warning is None
    assert mcp_seen[1].headers["Authorization"] == "Bearer tok-2"
    assert len(token_server.requests) == 2
    assert any(name == "mcp_credential_refreshed" for name, _ in events)


@pytest.mark.asyncio
async def test_egress_refresh_failure_fail_closed_never_sends_stale(
    monkeypatch, secret_env
):
    """Token-endpoint 500 on re-mint → auth failure; stale Bearer never upstream (#2281)."""
    token_server = TokenServer(expires_in=300)
    clock = FakeClock()
    monkeypatch.setattr(secret_refs, "_default_transport", token_server.transport)
    monkeypatch.setattr(secret_refs, "_now", clock)

    ref = _oauth_ref(secret_env)
    boot = resolve_secret_ref(ref)
    assert boot == "tok-1"

    mcp_seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "idp.example.com":
            return token_server.handler(request)
        mcp_seen.append(request)
        return _mcp_ok(request)

    class Patched(httpx.AsyncClient):
        def __init__(self, *args, **kwargs):
            kwargs["transport"] = httpx.MockTransport(handler)
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", Patched)

    provider = McpEgressProvider(
        McpServerConfig(
            id="demo",
            url=f"http://{MCP_HOST}/rpc",
            token=boot,
            triggers=["@mcp:demo"],
        )
    )
    req = InternalRequest(
        messages=[Message(role="user", content="@mcp:demo ping")],
        model="daari",
    )
    ok = await provider.execute(req)
    assert ok.daari_meta.warning is None
    assert mcp_seen[0].headers["Authorization"] == "Bearer tok-1"

    token_server.status = 500
    clock.advance(250)
    failed = await provider.execute(req)
    assert failed.daari_meta.warning == "mcp_credential_refresh_failed"
    assert "demo" in failed.content.lower() or "mcp:demo" in failed.content
    assert len(mcp_seen) == 1  # stale Bearer never sent upstream
