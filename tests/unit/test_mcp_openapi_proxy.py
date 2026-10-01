"""POST /mcp/proxy OpenAPI → MCP tools (#1264)."""

from __future__ import annotations

import httpx
import pytest
from httpx import ASGITransport, AsyncClient

from daari.auth.rate_families import rate_limit_family
from daari.config.settings import McpOpenApiSpecSettings
from daari.gateway.mcp_proxy import openapi_operations_to_tools
from daari.router.router import AppContext
from daari.server.app import create_app

_SPEC = {
    "openapi": "3.0.0",
    "info": {"title": "Pet", "version": "1.0.0"},
    "servers": [{"url": "https://api.example.com"}],
    "paths": {
        "/pets/{petId}": {
            "get": {
                "operationId": "getPet",
                "summary": "Fetch a pet",
                "parameters": [
                    {
                        "name": "petId",
                        "in": "path",
                        "required": True,
                        "schema": {"type": "string"},
                    }
                ],
            }
        }
    },
}


def _app(settings):
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    return app


def _patch_http(monkeypatch, handler):
    from daari.gateway import mcp_proxy

    mcp_proxy._http = None
    real = httpx.AsyncClient

    class Patched(real):
        def __init__(self, *args, **kwargs):
            if kwargs.get("transport") is None:
                kwargs["transport"] = httpx.MockTransport(handler)
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", Patched)
    monkeypatch.setattr("daari.gateway.mcp_proxy.httpx.AsyncClient", Patched)


def _allow_public_host(monkeypatch, host: str = "api.example.com"):
    """SSRF checks resolve DNS; map test hosts to a public address."""

    def fake_validate(url: str, *, allow_private_networks: bool = False, resolver=None):
        from daari.security.egress_url import validate_egress_url as real

        def resolve(name: str):
            if name == host:
                return ["1.1.1.1"]
            return ["1.1.1.1"]

        return real(url, allow_private_networks=allow_private_networks, resolver=resolve)

    monkeypatch.setattr("daari.gateway.mcp_proxy.validate_egress_url", fake_validate)


def test_openapi_conversion_happy_path():
    tools = openapi_operations_to_tools(_SPEC)
    assert len(tools) == 1
    assert tools[0]["name"] == "getPet"
    assert "petId" in tools[0]["inputSchema"]["properties"]


def test_rate_family_maps_mcp_proxy():
    assert rate_limit_family("/mcp/proxy") == "mcp"


def test_openapi_lists_mcp_proxy(settings):
    schema = create_app(settings).openapi()
    assert "/mcp/proxy" in schema["paths"]
    assert "post" in schema["paths"]["/mcp/proxy"]


@pytest.mark.asyncio
async def test_disabled_returns_503(settings):
    settings.integrations.mcp_openapi_proxy.enabled = False
    app = _app(settings)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/mcp/proxy",
            json={"action": "tools/list", "spec_id": "pets"},
        )
    assert response.status_code == 503
    assert response.json()["error"]["type"] == "service_unavailable"


@pytest.mark.asyncio
async def test_list_tools_from_allowlisted_spec(settings, monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/openapi.json"):
            return httpx.Response(200, json=_SPEC)
        raise AssertionError(f"unexpected {request.url}")

    _patch_http(monkeypatch, handler)
    _allow_public_host(monkeypatch)
    settings.integrations.mcp_openapi_proxy.enabled = True
    settings.integrations.mcp_openapi_proxy.specs = [
        McpOpenApiSpecSettings(
            id="pets",
            openapi_url="https://api.example.com/openapi.json",
            base_url="https://api.example.com",
        )
    ]
    settings.integrations.mcp_egress.allow_private_networks = False
    app = _app(settings)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/mcp/proxy",
            json={"action": "tools/list", "spec_id": "pets"},
        )

    assert response.status_code == 200, response.text
    tools = response.json()["tools"]
    assert tools[0]["name"] == "getPet"
    assert "_daari" not in tools[0]


@pytest.mark.asyncio
async def test_blocked_url_returns_400(settings, monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("must not fetch")

    _patch_http(monkeypatch, handler)
    settings.integrations.mcp_openapi_proxy.enabled = True
    settings.integrations.mcp_openapi_proxy.specs = [
        McpOpenApiSpecSettings(
            id="local",
            openapi_url="http://127.0.0.1:9/openapi.json",
        )
    ]
    settings.integrations.mcp_egress.allow_private_networks = False
    app = _app(settings)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/mcp/proxy",
            json={"action": "tools/list", "spec_id": "local"},
        )

    assert response.status_code == 400
    assert response.json()["error"]["type"] == "egress_blocked"


@pytest.mark.asyncio
async def test_tools_call_proxies_http(settings, monkeypatch):
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        if request.url.path.endswith("/openapi.json"):
            return httpx.Response(200, json=_SPEC)
        if request.url.path.endswith("/pets/42"):
            return httpx.Response(200, json={"id": "42", "name": "fido"})
        return httpx.Response(404, json={"error": "missing"})

    _patch_http(monkeypatch, handler)
    _allow_public_host(monkeypatch)
    settings.integrations.mcp_openapi_proxy.enabled = True
    settings.integrations.mcp_openapi_proxy.specs = [
        McpOpenApiSpecSettings(
            id="pets",
            openapi_url="https://api.example.com/openapi.json",
            base_url="https://api.example.com",
        )
    ]
    settings.integrations.mcp_egress.allow_private_networks = False
    app = _app(settings)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/mcp/proxy",
            json={
                "action": "tools/call",
                "spec_id": "pets",
                "name": "getPet",
                "arguments": {"petId": "42"},
            },
        )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["isError"] is False
    text = body["content"][0]["text"]
    assert "fido" in text
    assert any("/pets/42" in url for url in seen)


def test_mcp_docs_mention_proxy():
    from pathlib import Path

    text = (
        Path(__file__).resolve().parents[2] / "docs/developer/guides/clients/mcp.md"
    ).read_text(encoding="utf-8")
    assert "/mcp/proxy" in text
    assert "mcp_openapi_proxy" in text
