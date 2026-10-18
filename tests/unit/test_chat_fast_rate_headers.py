"""Copy Anthropic fast-mode rate-limit headers onto chat completions (#1766)."""

from __future__ import annotations

import json

import httpx
import pytest
from httpx import ASGITransport, AsyncClient

from daari.gateway.internal import DaariMeta, InternalRequest, InternalResponse
from daari.router.frontier import FrontierExecutor
from daari.router.router import AppContext
from daari.server.app import create_app
from tests.conftest import mock_all_ollama_executors


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


def _anthropic_sse() -> bytes:
    delta = {
        "type": "content_block_delta",
        "delta": {"type": "text_delta", "text": "from-frontier"},
    }
    text = (
        f"event: content_block_delta\ndata: {json.dumps(delta)}\n\n"
        'event: message_stop\ndata: {"type":"message_stop"}\n\n'
    )
    return text.encode()


def _openai_message() -> dict:
    return {
        "id": "chatcmpl-1",
        "choices": [
            {
                "message": {"role": "assistant", "content": "from-openai"},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 3, "completion_tokens": 2},
    }


async def _low_confidence(_request: InternalRequest) -> InternalResponse:
    return InternalResponse(
        content="no",
        model="llama3.2:3b",
        daari_meta=DaariMeta(tier="L3", executor="ollama", provider_id="ollama:l3"),
    )


async def _low_confidence_stream(_request: InternalRequest):
    yield {"message": {"content": "no"}, "done": True}


def _install_frontier(app, *, provider: str, handler) -> None:
    base = "https://api.anthropic.com" if provider == "anthropic" else "https://api.openai.com"
    model = "claude-opus-5-5" if provider == "anthropic" else "gpt-4o-mini"
    frontier = FrontierExecutor(
        base_url=base,
        default_model=model,
        api_key="sk-test",
        provider=provider,
        transport=httpx.MockTransport(handler),
    )
    app.state.ctx.router.frontier = frontier
    app.state.ctx.router.frontier_enabled = True


def _mock_local_stream(monkeypatch, router) -> None:
    seen: set[int] = set()
    for attr in ("ollama_l3", "ollama_l4", "ollama_l5", "ollama"):
        executor = getattr(router, attr, None)
        if executor is None or id(executor) in seen:
            continue
        seen.add(id(executor))
        monkeypatch.setattr(executor, "stream", _low_confidence_stream)


@pytest.mark.asyncio
async def test_chat_completions_copies_anthropic_fast_rate_headers(settings, monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content or b"{}")
        if body.get("stream"):
            return httpx.Response(
                200,
                content=_anthropic_sse(),
                headers={**_upstream_headers(), "content-type": "text/event-stream"},
            )
        return httpx.Response(200, json=_anthropic_message(), headers=_upstream_headers())

    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    _install_frontier(app, provider="anthropic", handler=handler)
    mock_all_ollama_executors(monkeypatch, app.state.ctx.router, _low_confidence)
    _mock_local_stream(monkeypatch, app.state.ctx.router)
    body = {
        "model": "claude-opus-5-5",
        "messages": [{"role": "user", "content": "hello there"}],
    }
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        plain = await client.post("/v1/chat/completions", json=body)
        streamed = await client.post("/v1/chat/completions", json={**body, "stream": True})
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


@pytest.mark.asyncio
async def test_chat_completions_openai_l6_omits_fast_rate_headers(settings, monkeypatch):
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_openai_message(), headers=_upstream_headers())

    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    _install_frontier(app, provider="openai", handler=handler)
    mock_all_ollama_executors(monkeypatch, app.state.ctx.router, _low_confidence)
    body = {
        "model": "gpt-4o-mini",
        "messages": [{"role": "user", "content": "hello there"}],
    }
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        plain = await client.post("/v1/chat/completions", json=body)
    assert plain.status_code == 200
    assert plain.headers.get("anthropic-fast-input-tokens-limit") is None
    assert plain.headers.get("anthropic-fast-output-tokens-reset") is None
    assert plain.headers.get("x-unrelated") is None
