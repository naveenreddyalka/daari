"""Doctor probes configured integrations.mcp_servers (#963)."""

from __future__ import annotations

import httpx

from daari.config.settings import McpServerSettings
from daari.setup.doctor import _check_mcp_servers, run_doctor


def _client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


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
