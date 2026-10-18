"""Image and document blocks add to local count_tokens (#1769)."""

from __future__ import annotations

import json

import httpx
import pytest
from httpx import ASGITransport, AsyncClient

from daari.observability.tokens import estimate_tokens
from daari.router.frontier import FrontierExecutor
from daari.router.router import AppContext
from daari.server.app import create_app
from tests.conftest import META_HEADERS


def _expected_text_tokens(*parts: str) -> int:
    chars = sum(len(part) for part in parts)
    return max(1, estimate_tokens(chars))


async def _post(app, body: dict) -> dict:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/messages/count_tokens",
            json=body,
            headers=META_HEADERS,
        )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert set(payload) == {"input_tokens"}
    assert isinstance(payload["input_tokens"], int)
    return payload


@pytest.mark.asyncio
async def test_count_tokens_text_only_matches_estimate(settings):
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    system = "you are brief"
    text = "hello there friend"
    tools = [{"name": "ping", "input_schema": {"type": "object"}}]
    payload = await _post(
        app,
        {
            "model": "daari",
            "system": system,
            "tools": tools,
            "messages": [{"role": "user", "content": text}],
        },
    )
    assert payload["input_tokens"] == _expected_text_tokens(system, text, json.dumps(tools))


@pytest.mark.asyncio
async def test_count_tokens_image_and_document_add_tokens(settings):
    def handler(_request: httpx.Request) -> httpx.Response:
        raise AssertionError("count_tokens must not call L6")

    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    app.state.ctx.router.frontier = FrontierExecutor(
        base_url="https://api.anthropic.com",
        default_model="claude-sonnet-4-0",
        api_key="sk-ant-test",
        provider="anthropic",
        transport=httpx.MockTransport(handler),
    )
    app.state.ctx.router.frontier_enabled = True
    text = "hello there friend"
    text_only = await _post(
        app,
        {
            "model": "daari",
            "messages": [{"role": "user", "content": text}],
        },
    )
    one_image = await _post(
        app,
        {
            "model": "daari",
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": text},
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/png",
                                "data": "abc",
                            },
                        },
                    ],
                }
            ],
        },
    )
    openai_image = await _post(
        app,
        {
            "model": "daari",
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": text},
                        {"type": "image_url", "image_url": {"url": "https://example.test/a.png"}},
                    ],
                }
            ],
        },
    )
    two_images = await _post(
        app,
        {
            "model": "daari",
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": text},
                        {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": "abc"}},
                        {"type": "image_url", "image_url": {"url": "https://example.test/b.png"}},
                    ],
                }
            ],
        },
    )
    document = await _post(
        app,
        {
            "model": "daari",
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": text},
                        {
                            "type": "document",
                            "source": {"type": "base64", "media_type": "application/pdf", "data": "pdf"},
                        },
                    ],
                }
            ],
        },
    )
    base = text_only["input_tokens"]
    assert one_image["input_tokens"] >= base + 1
    assert openai_image["input_tokens"] >= base + 1
    assert document["input_tokens"] >= base + 1
    assert two_images["input_tokens"] > one_image["input_tokens"]
