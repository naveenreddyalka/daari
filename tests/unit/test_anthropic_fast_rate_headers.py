"""Copy Anthropic fast-mode rate-limit headers onto Messages responses (#1756)."""

from __future__ import annotations

import json

import httpx
import pytest
from httpx import ASGITransport, AsyncClient

from daari.gateway.internal import InternalRequest, Message
from daari.router.frontier import (
    ANTHROPIC_FAST_RATE_HEADERS,
    FrontierExecutor,
    anthropic_fast_rate_headers,
)
from daari.router.router import AppContext
from daari.server.app import create_app
from tests.conftest import mock_all_ollama_executors


def test_fast_rate_header_allowlist_drops_unrelated_names() -> None:
    found = anthropic_fast_rate_headers(
        httpx.Headers(
            {
                "anthropic-fast-input-tokens-limit": "1000",
                "anthropic-fast-output-tokens-remaining": "4",
                "x-request-id": "upstream",
                "anthropic-fast-input-tokens-reset": "",
            }
        )
    )
    assert found == {
        "anthropic-fast-input-tokens-limit": "1000",
        "anthropic-fast-output-tokens-remaining": "4",
    }
    assert set(ANTHROPIC_FAST_RATE_HEADERS) == {
        "anthropic-fast-input-tokens-limit",
        "anthropic-fast-input-tokens-remaining",
        "anthropic-fast-input-tokens-reset",
        "anthropic-fast-output-tokens-limit",
        "anthropic-fast-output-tokens-remaining",
        "anthropic-fast-output-tokens-reset",
    }


def _anthropic_message() -> dict:
    return {
        "id": "msg_1",
        "type": "message",
        "role": "assistant",
        "model": "claude-opus-5-5",
        "stop_reason": "end_turn",
        "content": [{"type": "text", "text": "from-frontier"}],
        "usage": {"input_tokens": 3, "output_tokens": 2},
    }


def _upstream_headers() -> dict[str, str]:
    return {
        "anthropic-fast-input-tokens-limit": "1000",
        "anthropic-fast-input-tokens-remaining": "800",
        "anthropic-fast-output-tokens-reset": "2026-10-18T13:00:00Z",
        "x-unrelated": "nope",
    }


@pytest.mark.asyncio
async def test_frontier_execute_and_stream_capture_fast_rate_headers() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        if _request.url.path.endswith("/messages") and json.loads(_request.content).get("stream"):
            body = (
                b'event: message_stop\ndata: {"type":"message_stop"}\n\n'
            )
            return httpx.Response(
                200,
                content=body,
                headers={**_upstream_headers(), "content-type": "text/event-stream"},
            )
        return httpx.Response(200, json=_anthropic_message(), headers=_upstream_headers())

    executor = FrontierExecutor(
        base_url="https://api.anthropic.com",
        default_model="claude-opus-5-5",
        api_key="sk-ant-test",
        provider="anthropic",
        transport=httpx.MockTransport(handler),
    )
    request = InternalRequest(
        messages=[Message(role="user", content="hi")],
        model="claude-opus-5-5",
    )
    await executor.execute(request, escalated_from="L3", local_confidence=0.0)
    assert executor.last_fast_rate_headers == {
        "anthropic-fast-input-tokens-limit": "1000",
        "anthropic-fast-input-tokens-remaining": "800",
        "anthropic-fast-output-tokens-reset": "2026-10-18T13:00:00Z",
    }
    assert "x-unrelated" not in executor.last_fast_rate_headers
    _ = [event async for event in executor.stream(request)]
    assert executor.last_fast_rate_headers["anthropic-fast-input-tokens-limit"] == "1000"
    assert "x-unrelated" not in executor.last_fast_rate_headers


@pytest.mark.asyncio
async def test_messages_gateway_copies_fast_rate_headers(settings, monkeypatch):
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_anthropic_message(), headers=_upstream_headers())

    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    frontier = FrontierExecutor(
        base_url="https://api.anthropic.com",
        default_model="claude-opus-5-5",
        api_key="sk-ant-test",
        provider="anthropic",
        transport=httpx.MockTransport(handler),
    )
    app.state.ctx.router.frontier = frontier
    app.state.ctx.router.frontier_enabled = True

    async def low_confidence(_request: InternalRequest):
        from daari.gateway.internal import DaariMeta, InternalResponse

        return InternalResponse(
            content="no",
            model="llama3.2:3b",
            daari_meta=DaariMeta(tier="L3", executor="ollama", provider_id="ollama:l3"),
        )

    mock_all_ollama_executors(monkeypatch, app.state.ctx.router, low_confidence)
    body = {
        "model": "claude-opus-5-5",
        "max_tokens": 32,
        "messages": [{"role": "user", "content": "hello there"}],
    }
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        plain = await client.post("/v1/messages", json=body)
        streamed = await client.post("/v1/messages", json={**body, "stream": True})
    assert plain.status_code == 200
    assert plain.headers["anthropic-fast-input-tokens-limit"] == "1000"
    assert plain.headers["anthropic-fast-input-tokens-remaining"] == "800"
    assert plain.headers["anthropic-fast-output-tokens-reset"] == "2026-10-18T13:00:00Z"
    assert "anthropic-fast-output-tokens-limit" not in plain.headers
    assert plain.headers.get("x-unrelated") is None
    assert streamed.status_code == 200
    assert streamed.headers["anthropic-fast-input-tokens-limit"] == "1000"
    assert "anthropic-fast-input-tokens-remaining" in streamed.headers
    assert streamed.headers.get("x-unrelated") is None
    assert "anthropic-fast-output-tokens-limit" not in streamed.headers
