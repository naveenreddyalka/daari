"""Per-server MCP egress request timeout (#1995)."""

from __future__ import annotations

import socket

import httpx
import pytest
from pydantic import ValidationError

from daari.config.settings import McpServerSettings
from daari.gateway.internal import InternalRequest, Message
from daari.observability.metrics import Metrics
from daari.providers.mcp_egress import McpEgressProvider, McpServerConfig, build_mcp_providers
from daari.router.circuit_breaker import CircuitBreaker
from daari.router.retry import RetryPolicy

_FAST = RetryPolicy(attempts=1, base_delay=0.0, max_delay=0.0, jitter=0.0)


@pytest.fixture(autouse=True)
def _public_dns_for_fake_mcp_hosts(monkeypatch):
    def fake_getaddrinfo(host, port, *args, **kwargs):
        return [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port or 0))
        ]

    monkeypatch.setattr("daari.security.egress_url.socket.getaddrinfo", fake_getaddrinfo)


def test_mcp_server_settings_timeout_default_and_reject_negative():
    entry = McpServerSettings(id="demo", url="http://mcp.test/rpc")
    assert entry.timeout_seconds == 0.0
    custom = McpServerSettings(id="demo", url="http://mcp.test/rpc", timeout_seconds=5.5)
    assert custom.timeout_seconds == 5.5
    with pytest.raises(ValidationError):
        McpServerSettings(id="demo", url="http://mcp.test/rpc", timeout_seconds=-1)


def test_build_mcp_providers_copies_timeout_seconds():
    providers = build_mcp_providers(
        [McpServerSettings(id="demo", url="http://mcp.test/rpc", timeout_seconds=12.0)]
    )
    assert len(providers) == 1
    assert providers[0].server.timeout_seconds == 12.0


def test_default_http_timeout_unchanged(monkeypatch):
    seen_timeouts: list[object] = []

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"jsonrpc": "2.0", "id": 1, "result": {"ok": True}}
        )

    class Patched(httpx.AsyncClient):
        def __init__(self, *args, **kwargs):
            seen_timeouts.append(kwargs.get("timeout"))
            kwargs["transport"] = httpx.MockTransport(handler)
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", Patched)
    provider = McpEgressProvider(McpServerConfig(id="demo", url="http://mcp.test/rpc"))
    assert provider.list_timeout_seconds == 15.0
    # Force client construction
    client = provider._client()
    assert client is not None
    assert seen_timeouts[-1] == 30.0


def test_per_server_timeout_applied_to_client_and_list_deadline(monkeypatch):
    seen_timeouts: list[object] = []

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"jsonrpc": "2.0", "id": 1, "result": {"ok": True}}
        )

    class Patched(httpx.AsyncClient):
        def __init__(self, *args, **kwargs):
            seen_timeouts.append(kwargs.get("timeout"))
            kwargs["transport"] = httpx.MockTransport(handler)
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", Patched)
    provider = McpEgressProvider(
        McpServerConfig(id="demo", url="http://mcp.test/rpc", timeout_seconds=7.5)
    )
    assert provider.list_timeout_seconds == 7.5
    provider._client()
    assert seen_timeouts[-1] == 7.5


@pytest.mark.asyncio
async def test_timeout_error_trips_breaker_and_failure_path(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow mcp")

    class Patched(httpx.AsyncClient):
        def __init__(self, *args, **kwargs):
            kwargs["transport"] = httpx.MockTransport(handler)
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", Patched)
    metrics = Metrics()
    breaker = CircuitBreaker(failure_threshold=1, cooldown_seconds=60.0)
    provider = McpEgressProvider(
        McpServerConfig(id="demo", url="http://mcp.test/rpc", timeout_seconds=1.0),
        retry=_FAST,
        breaker=breaker,
        metrics=metrics,
    )
    result = await provider.execute(
        InternalRequest(
            messages=[Message(role="user", content="@mcp:demo ping")],
            model="daari",
        )
    )
    assert result.daari_meta.warning == "integration_request_failed"
    assert breaker.state == "open"
    snap = metrics.snapshot(include_histograms=True)
    assert any(
        key.startswith("demo:") and ":error" in key
        for key in (snap.get("mcp_egress") or {})
    )
