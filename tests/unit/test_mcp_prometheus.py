"""Prometheus counters for MCP ingress tool calls (#603)."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from daari.auth.virtual_keys import VirtualKeyStore
from daari.gateway.internal import DaariMeta, InternalRequest, InternalResponse
from daari.observability.metrics import Metrics
from daari.observability.prometheus import render_prometheus
from daari.router.router import AppContext
from daari.server.app import create_app
from tests.conftest import META_HEADERS, mock_all_ollama_executors


def test_mcp_tool_calls_prometheus_render():
    metrics = Metrics()
    metrics.record_mcp_tool_call(tool="route", outcome="ok")
    metrics.record_mcp_tool_call(tool="stats", outcome="deny")
    metrics.record_mcp_tool_call(tool="stats", outcome="deny")
    text = render_prometheus(metrics)
    assert "# TYPE daari_mcp_tool_calls_total counter" in text
    assert 'daari_mcp_tool_calls_total{tool="route",outcome="ok"} 1' in text
    assert 'daari_mcp_tool_calls_total{tool="stats",outcome="deny"} 2' in text


def _app(settings, monkeypatch, *, metadata=None):
    settings.observability.prometheus = True
    store = VirtualKeyStore(settings.virtual_keys_path)
    created = store.create("agent", client_id="agent", metadata=metadata)
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    app.state.virtual_key_store = store
    app.state.ctx.virtual_key_store = store

    async def fake_execute(_request: InternalRequest) -> InternalResponse:
        return InternalResponse(
            content="routed",
            model="llama3.2:3b",
            daari_meta=DaariMeta(tier="L3", executor="ollama", provider_id="ollama:l3"),
        )

    mock_all_ollama_executors(monkeypatch, app.state.ctx.router, fake_execute)
    return app, {"Authorization": f"Bearer {created.plaintext}", **META_HEADERS}


async def _rpc(client, method, params=None, *, headers, rpc_id=1):
    body = {"jsonrpc": "2.0", "id": rpc_id, "method": method}
    if params is not None:
        body["params"] = params
    return await client.post("/mcp", json=body, headers=headers)


@pytest.mark.asyncio
async def test_mcp_ok_and_deny_appear_in_metrics(settings, monkeypatch, tmp_path):
    settings.server.virtual_keys.path = str(tmp_path / "vk.sqlite3")
    settings.server.api_key = "master"
    app, headers = _app(settings, monkeypatch, metadata={"mcp": {"deny": ["stats"]}})

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        ok = await _rpc(
            client,
            "tools/call",
            {"name": "route", "arguments": {"input": "hello"}},
            headers=headers,
        )
        denied = await _rpc(
            client,
            "tools/call",
            {"name": "stats", "arguments": {}},
            headers=headers,
            rpc_id=2,
        )
        metrics = await client.get("/metrics", headers={"Authorization": "Bearer master"})

    assert ok.status_code == 200
    assert "result" in ok.json()
    assert denied.status_code == 200
    assert denied.json().get("error") is not None
    assert metrics.status_code == 200
    body = metrics.text
    assert "# TYPE daari_mcp_tool_calls_total counter" in body
    assert 'daari_mcp_tool_calls_total{tool="route",outcome="ok"} 1' in body
    assert 'daari_mcp_tool_calls_total{tool="stats",outcome="deny"} 1' in body


@pytest.mark.asyncio
async def test_mcp_metrics_noop_when_prometheus_disabled(settings, monkeypatch, tmp_path):
    settings.server.virtual_keys.path = str(tmp_path / "vk.sqlite3")
    settings.server.api_key = "master"
    settings.observability.prometheus = False
    store = VirtualKeyStore(settings.virtual_keys_path)
    created = store.create("agent", client_id="agent")
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    app.state.virtual_key_store = store
    app.state.ctx.virtual_key_store = store

    async def fake_execute(_request: InternalRequest) -> InternalResponse:
        return InternalResponse(
            content="routed",
            model="llama3.2:3b",
            daari_meta=DaariMeta(tier="L3", executor="ollama", provider_id="ollama:l3"),
        )

    mock_all_ollama_executors(monkeypatch, app.state.ctx.router, fake_execute)
    headers = {"Authorization": f"Bearer {created.plaintext}", **META_HEADERS}

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await _rpc(
            client,
            "tools/call",
            {"name": "route", "arguments": {"input": "hello"}},
            headers=headers,
        )

    snap = app.state.ctx.router.metrics.snapshot(include_histograms=True)
    assert not snap.get("mcp_tool_calls")
