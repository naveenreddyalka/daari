"""Per-server rpm/tpm ceilings on integrations.mcp_servers (#1620)."""

from __future__ import annotations

import json
import socket

import httpx
import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError

from daari.auth.rate_limit import MemoryCounterBackend, RateLimiter
from daari.auth.virtual_keys import VirtualKeyStore
from daari.config.settings import McpServerSettings
from daari.providers.mcp_egress import McpEgressProvider, McpServerConfig, build_mcp_providers
from daari.router.router import AppContext
from daari.server.app import create_app
from daari.setup.doctor import _check_mcp_server_rate_limits, run_doctor


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


def _wire_app(settings):
    application = create_app(settings)
    application.state.ctx = AppContext.from_settings(settings)
    limiter = application.state.rate_limiter
    application.state.ctx.rate_limiter = limiter
    registry = application.state.ctx.providers
    for sid in [
        str(getattr(s, "id", "") or "")
        for s in (settings.integrations.mcp_servers or [])
    ]:
        if not sid:
            continue
        provider = registry.get(f"mcp:{sid}")
        if isinstance(provider, McpEgressProvider):
            provider.rate_limiter = limiter
    return application


def test_mcp_server_settings_accept_rpm_tpm():
    entry = McpServerSettings(id="demo", url="http://mcp.test/rpc", rpm=10, tpm=1000)
    assert entry.rpm == 10
    assert entry.tpm == 1000
    unlimited = McpServerSettings(id="demo", url="http://mcp.test/rpc")
    assert unlimited.rpm == 0
    assert unlimited.tpm == 0


def test_mcp_server_settings_reject_negative_rpm_tpm():
    with pytest.raises(ValidationError):
        McpServerSettings(id="demo", url="http://mcp.test/rpc", rpm=-1)
    with pytest.raises(ValidationError):
        McpServerSettings(id="demo", url="http://mcp.test/rpc", tpm=-1)


def test_build_mcp_providers_copies_rpm_tpm():
    providers = build_mcp_providers(
        [McpServerSettings(id="demo", url="http://mcp.test/rpc", rpm=3, tpm=50)]
    )
    assert len(providers) == 1
    assert providers[0].server.rpm == 3
    assert providers[0].server.tpm == 50


def test_check_mcp_server_trips_independently():
    limiter = RateLimiter(MemoryCounterBackend(), default_rpm=0, default_tpm=0)
    first = limiter.check_mcp_server(server_id="demo", tokens=1, rpm=1, tpm=0)
    second = limiter.check_mcp_server(server_id="demo", tokens=1, rpm=1, tpm=0)
    assert first.allowed
    assert not second.allowed
    assert second.bucket == "mcp_server:demo"
    assert second.retry_after is not None
    headers = second.headers()
    assert headers.get("Retry-After")
    assert headers.get("X-RateLimit-Scope") == "mcp_server:demo"


@pytest.mark.asyncio
async def test_per_server_rpm_trips_while_key_family_allows(settings, monkeypatch, tmp_path):
    settings.server.api_key = "master"
    settings.server.virtual_keys.path = str(tmp_path / "vk.sqlite3")
    settings.rate_limit.rpm = 0
    settings.rate_limit.tpm = 0
    settings.integrations.mcp_aggregate_egress.enabled = True
    settings.integrations.mcp_servers = [
        McpServerSettings(id="demo", url="http://mcp.test/rpc", rpm=1, tpm=0),
    ]
    store = VirtualKeyStore(settings.virtual_keys_path)
    created = store.create(
        "scoped",
        metadata={"rate_families": {"mcp": {"rpm": 50}}},
    )
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        body = json.loads(request.content.decode())
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
                                "description": "ping",
                                "inputSchema": {"type": "object", "properties": {}},
                            }
                        ]
                    },
                },
            )
        calls += 1
        return httpx.Response(
            200,
            json={
                "jsonrpc": "2.0",
                "id": body.get("id", 1),
                "result": {"content": [{"type": "text", "text": "pong"}]},
            },
        )

    monkeypatch.setattr(httpx, "AsyncClient", _patched_client(handler))
    app = _wire_app(settings)
    app.state.virtual_key_store = store
    app.state.ctx.virtual_key_store = store
    headers = {"Authorization": f"Bearer {created.plaintext}"}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        first = await client.post(
            "/mcp",
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": "demo__ping", "arguments": {}},
            },
            headers=headers,
        )
        second = await client.post(
            "/mcp",
            json={
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {"name": "demo__ping", "arguments": {}},
            },
            headers=headers,
        )

    assert first.status_code == 200, first.text
    assert second.status_code == 429, second.text
    body = second.json()
    assert body["error"]["type"] == "rate_limit_error"
    assert "mcp_server:demo" in body["error"]["message"]
    assert second.headers.get("Retry-After")
    assert second.headers.get("X-RateLimit-Scope") == "mcp_server:demo"
    assert calls == 1


def test_doctor_tip_when_server_rpm_set(settings):
    settings.integrations.mcp_servers = [
        McpServerSettings(id="noisy", url="http://mcp.test/rpc", rpm=30),
    ]
    row = _check_mcp_server_rate_limits(settings)
    assert row is not None
    assert row.name == "mcp_server_rate_limits"
    assert row.optional is True
    assert row.ok is True
    detail = row.detail.lower()
    assert "noisy" in detail
    assert "rpm" in detail


def test_doctor_tip_absent_when_no_ceilings(settings):
    settings.integrations.mcp_servers = [
        McpServerSettings(id="demo", url="http://mcp.test/rpc"),
    ]
    assert _check_mcp_server_rate_limits(settings) is None
    rows = run_doctor(settings, httpx_client=None)
    assert not any(r.name == "mcp_server_rate_limits" for r in rows)


def test_docs_mention_mcp_server_rpm_tpm():
    from pathlib import Path

    config = Path("docs/developer/reference/config.md").read_text()
    assert "rpm" in config.lower()
    assert "integrations.mcp_servers" in config
    assert "tpm" in config
    mcp = Path("docs/developer/guides/clients/mcp.md").read_text()
    assert "mcp_server" in mcp.lower() or "per-server" in mcp.lower()
    doctor = Path("docs/developer/guides/operations/doctor-health.md").read_text()
    assert "mcp_server_rate_limits" in doctor


def test_mcp_server_config_defaults_unlimited():
    cfg = McpServerConfig(id="demo", url="http://mcp.test/rpc")
    assert cfg.rpm == 0
    assert cfg.tpm == 0
