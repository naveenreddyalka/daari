"""POST /v1/responses/input_tokens (#507)."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from daari.observability.tokens import estimate_tokens
from daari.router.router import AppContext
from daari.server.app import create_app
from tests.conftest import META_HEADERS


@pytest.mark.asyncio
async def test_responses_input_tokens_counts_string_input(settings):
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    text = "hello there friend"
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/v1/responses/input_tokens",
            json={"model": "daari", "input": text},
            headers=META_HEADERS,
        )
    assert response.status_code == 200, response.text
    assert response.json()["input_tokens"] == max(1, estimate_tokens(len(text)))


@pytest.mark.asyncio
async def test_responses_input_tokens_includes_instructions_and_tools(settings):
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    payload = {
        "model": "daari",
        "input": "hi",
        "instructions": "be brief",
        "tools": [{"type": "function", "name": "lookup", "parameters": {}}],
    }
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/v1/responses/input_tokens",
            json=payload,
            headers=META_HEADERS,
        )
    assert response.status_code == 200, response.text
    assert response.json()["input_tokens"] > max(1, estimate_tokens(len("hi")))


@pytest.mark.asyncio
async def test_responses_input_tokens_empty_input_still_returns_count(settings):
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/v1/responses/input_tokens",
            json={"model": "daari", "input": ""},
            headers=META_HEADERS,
        )
    assert response.status_code == 200, response.text
    assert response.json()["input_tokens"] >= 1


@pytest.mark.asyncio
async def test_responses_input_tokens_malformed_body_422(settings):
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/v1/responses/input_tokens",
            json={"model": "daari", "input": 12345},
            headers=META_HEADERS,
        )
    assert response.status_code == 422
