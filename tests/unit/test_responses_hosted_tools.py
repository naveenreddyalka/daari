"""Reject unsupported Responses hosted tool types (#1135)."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from daari.gateway.internal import DaariMeta, InternalRequest, InternalResponse
from daari.gateway.responses import (
    _SUPPORTED_TOOL_TYPES,
    unsupported_responses_tools,
)
from daari.router.router import AppContext
from daari.server.app import create_app

DOC = (
    __import__("pathlib").Path(__file__).resolve().parents[2]
    / "docs/developer/concepts/clients-and-gateways.md"
)


def test_supported_tool_types_are_function_only():
    assert _SUPPORTED_TOOL_TYPES == frozenset({"function"})


def test_unsupported_responses_tools_lists_hosted_types():
    bad = unsupported_responses_tools(
        [
            {"type": "function", "name": "ok", "parameters": {}},
            {"type": "web_search"},
            {"type": "mcp", "server_label": "x"},
        ]
    )
    assert bad == ["web_search", "mcp"]
    assert unsupported_responses_tools([{"type": "function", "name": "only"}]) == []
    assert unsupported_responses_tools(None) == []


def test_clients_and_gateways_docs_hosted_tools():
    text = DOC.read_text(encoding="utf-8")
    assert "hosted" in text.lower() or "web_search" in text
    assert "function" in text
    assert "400" in text


@pytest.mark.asyncio
async def test_web_search_tool_returns_400(settings):
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)

    async def fake_route(request: InternalRequest) -> InternalResponse:
        return InternalResponse(
            content="should not run",
            model="m",
            daari_meta=DaariMeta(tier="L3", executor="ollama", latency_ms=1),
        )

    app.state.ctx.router.route = fake_route
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/responses",
            json={
                "model": "daari",
                "input": "hi",
                "tools": [{"type": "web_search"}],
            },
        )
    assert response.status_code == 400
    detail = response.json()["detail"]
    assert "web_search" in detail
    assert "supported:" in detail
    assert "function" in detail


@pytest.mark.asyncio
async def test_mixed_function_and_hosted_tool_returns_400(settings):
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    app.state.ctx.router.route = lambda request: None  # type: ignore[assignment]
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/responses",
            json={
                "model": "daari",
                "input": "hi",
                "tools": [
                    {
                        "type": "function",
                        "name": "lookup",
                        "description": "d",
                        "parameters": {"type": "object", "properties": {}},
                    },
                    {"type": "web_search"},
                ],
            },
        )
    assert response.status_code == 400
    assert "web_search" in response.json()["detail"]


@pytest.mark.asyncio
async def test_function_only_tools_still_succeed(settings):
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)

    async def fake_route(request: InternalRequest) -> InternalResponse:
        fake_route.last_request = request
        return InternalResponse(
            content="ok",
            model="m",
            daari_meta=DaariMeta(tier="L3", executor="ollama", latency_ms=1),
        )

    app.state.ctx.router.route = fake_route
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/responses",
            json={
                "model": "daari",
                "input": "hi",
                "tools": [
                    {
                        "type": "function",
                        "name": "lookup",
                        "description": "d",
                        "parameters": {"type": "object", "properties": {}},
                    }
                ],
            },
        )
    assert response.status_code == 200, response.text
    assert fake_route.last_request.tools
    assert fake_route.last_request.tools[0]["type"] == "function"
