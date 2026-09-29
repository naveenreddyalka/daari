"""Doctor probes configured integrations.mcp_servers (#963)."""

from __future__ import annotations

import socket

import httpx
import pytest

from daari.config.settings import McpServerSettings
from daari.setup.doctor import _check_mcp_servers, run_doctor


def _client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


@pytest.fixture(autouse=True)
def _public_dns_for_fake_mcp_hosts(monkeypatch):
    def fake_getaddrinfo(host, port, *args, **kwargs):
        return [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port or 0))
        ]

    monkeypatch.setattr("daari.security.egress_url.socket.getaddrinfo", fake_getaddrinfo)


def test_empty_mcp_servers_adds_no_rows(settings):
    settings.integrations.mcp_servers = []
    assert _check_mcp_servers(settings, None) == []
    names = [item.name for item in run_doctor(settings, httpx_client=_client(lambda r: httpx.Response(200)))]
    assert not any(name.startswith("mcp:") for name in names)


def test_reachable_mcp_server(settings):
    settings.integrations.mcp_servers = [
        McpServerSettings(id="weather", url="http://mcp.local/v1", token="secret"),
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url).rstrip("/") == "http://mcp.local/v1"
        assert request.method == "POST"
        assert request.headers.get("Authorization") == "Bearer secret"
        body = request.read()
        assert b"initialize" in body or b"tools/list" in body
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": 1, "result": {}})

    rows = _check_mcp_servers(settings, _client(handler))
    assert len(rows) == 1
    assert rows[0].name == "mcp:weather"
    assert rows[0].ok
    assert rows[0].optional
    assert "reachable" in rows[0].detail


def test_unreachable_mcp_server_warns(settings):
    settings.integrations.mcp_servers = [
        McpServerSettings(id="dead", url="http://mcp.dead/"),
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    rows = _check_mcp_servers(settings, _client(handler))
    assert len(rows) == 1
    assert rows[0].name == "mcp:dead"
    assert not rows[0].ok
    assert rows[0].optional
    assert "unreachable" in rows[0].detail


def test_http_error_is_unreachable(settings):
    settings.integrations.mcp_servers = [
        McpServerSettings(id="bad", url="http://mcp.bad"),
    ]
    rows = _check_mcp_servers(settings, _client(lambda request: httpx.Response(503)))
    assert len(rows) == 1
    assert not rows[0].ok
    assert "503" in rows[0].detail


def test_run_doctor_includes_mcp_rows(settings):
    settings.integrations.mcp_servers = [
        McpServerSettings(id="a", url="http://a.local"),
        McpServerSettings(id="b", url="http://b.local"),
    ]
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": 1, "result": {}})

    names = [
        item.name
        for item in run_doctor(settings, httpx_client=_client(handler))
        if item.name.startswith("mcp:")
    ]
    assert names == ["mcp:a", "mcp:b"]
    assert len(seen) >= 2


def test_private_mcp_url_blocked_without_probe(settings):
    """Doctor fails closed on SSRF-risky MCP URLs and does not POST (#1214)."""
    settings.integrations.mcp_servers = [
        McpServerSettings(id="meta", url="http://169.254.169.254/latest"),
    ]
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return httpx.Response(200)

    rows = _check_mcp_servers(settings, _client(handler))
    assert len(rows) == 1
    assert not rows[0].ok
    assert "blocked" in rows[0].detail.lower()
    assert seen == []


def test_private_mcp_url_allowed_when_opted_in(settings):
    settings.integrations.mcp_egress.allow_private_networks = True
    settings.integrations.mcp_servers = [
        McpServerSettings(id="lab", url="http://10.0.0.1/mcp"),
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": 1, "result": {}})

    rows = _check_mcp_servers(settings, _client(handler))
    assert len(rows) == 1
    assert rows[0].ok
