"""Opt-in GET /v1/mcp/registry.json discovery (#1277)."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from daari.config.settings import McpServerSettings
from daari.gateway.mcp_registry import (
    build_registry_document,
    mcp_registry_enabled,
)
from daari.router.router import AppContext
from daari.server.app import create_app


def test_flag_defaults_off(settings):
    assert mcp_registry_enabled(settings) is False
    assert settings.integrations.mcp_registry.enabled is False


def test_registry_document_lists_builtin_and_egress(settings):
    settings.integrations.mcp_registry.enabled = True
    settings.integrations.mcp_registry.public_base_url = "http://gateway.example"
    settings.integrations.mcp_servers = [
        McpServerSettings(id="weather", url="https://mcp.weather.example/mcp"),
    ]
    doc = build_registry_document(settings)
    assert doc["servers"][0]["name"] == "daari"
    assert doc["servers"][0]["url"] == "http://gateway.example/mcp"
    assert doc["servers"][1]["name"] == "weather"
    assert doc["servers"][1]["url"] == "https://mcp.weather.example/mcp"


@pytest.mark.asyncio
async def test_registry_404_when_disabled(settings):
    settings.integrations.mcp_registry.enabled = False
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/v1/mcp/registry.json")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_registry_served_when_enabled(settings):
    settings.integrations.mcp_registry.enabled = True
    settings.integrations.mcp_servers = [
        McpServerSettings(id="shell", url="https://mcp.shell.example/mcp"),
    ]
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/v1/mcp/registry.json")
    assert response.status_code == 200
    body = response.json()
    names = [s["name"] for s in body["servers"]]
    assert names == ["daari", "shell"]
    assert body["servers"][0]["url"].endswith("/mcp")


@pytest.mark.asyncio
async def test_registry_auth_agnostic_when_api_key_set(settings):
    settings.server.api_key = "secret"
    settings.integrations.mcp_registry.enabled = True
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/v1/mcp/registry.json")
    assert response.status_code == 200
    assert response.json()["servers"][0]["name"] == "daari"
