"""Local-tier thinking capture: Ollama message.thinking + OpenAI-compat reasoning_content (#2299)."""

from __future__ import annotations

import json

import httpx
import pytest
from httpx import ASGITransport, AsyncClient

from daari.cache.exact import ExactCache
from daari.gateway.internal import DaariMeta, InternalRequest, InternalResponse, Message
from daari.gateway.openai import build_chat_completion_payload
from daari.gateway.responses import _output_items_from_result
from daari.router.openai_encrypted_reasoning import anthropic_content_with_encrypted_reasoning
from daari.router.openai_executor import OpenAICompatExecutor
from daari.router.router import AppContext, OllamaExecutor
from daari.server.app import create_app
from tests.conftest import META_HEADERS


def _patch_router_http(monkeypatch, handler) -> None:
    transport = httpx.MockTransport(handler)
    original = httpx.AsyncClient

    def patched(*args, **kwargs):
        kwargs["transport"] = transport
        return original(*args, **kwargs)

    monkeypatch.setattr("daari.router.router.httpx.AsyncClient", patched)


def _patch_openai_http(monkeypatch, handler) -> None:
    transport = httpx.MockTransport(handler)
    original = httpx.AsyncClient

    def patched(*args, **kwargs):
        kwargs["transport"] = transport
        return original(*args, **kwargs)

    monkeypatch.setattr("daari.router.openai_executor.httpx.AsyncClient", patched)


@pytest.mark.asyncio
async def test_ollama_execute_captures_thinking(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "message": {
                    "role": "assistant",
                    "content": "42",
                    "thinking": "count carefully",
                },
                "done": True,
            },
        )

    _patch_router_http(monkeypatch, handler)
    executor = OllamaExecutor(base_url="http://test", default_model="deepseek-r1:8b")
    response = await executor.execute(
        InternalRequest(
            model="deepseek-r1:8b",
            messages=[Message(role="user", content="answer?")],
        )
    )
    assert response.content == "42"
    assert response.reasoning_content == "count carefully"


@pytest.mark.asyncio
async def test_ollama_execute_no_thinking_unchanged(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"message": {"role": "assistant", "content": "plain"}, "done": True},
        )

    _patch_router_http(monkeypatch, handler)
    executor = OllamaExecutor(base_url="http://test", default_model="llama3.2:3b")
    response = await executor.execute(
        InternalRequest(model="llama3.2:3b", messages=[Message(role="user", content="hi")])
    )
    assert response.content == "plain"
    assert response.reasoning_content is None


@pytest.mark.asyncio
async def test_openai_compat_execute_captures_reasoning_content(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": "done",
                            "reasoning_content": "step by step",
                        },
                        "finish_reason": "stop",
                    }
                ]
            },
        )

    _patch_openai_http(monkeypatch, handler)
    executor = OpenAICompatExecutor(
        base_url="http://127.0.0.1:8000",
        default_model="qwen3",
        tier="L4",
    )
    response = await executor.execute(
        InternalRequest(model="qwen3", messages=[Message(role="user", content="hi")])
    )
    assert response.content == "done"
    assert response.reasoning_content == "step by step"


@pytest.mark.asyncio
async def test_openai_compat_stream_forwards_reasoning_content(monkeypatch):
    sse_body = (
        'data: {"choices":[{"delta":{"role":"assistant","reasoning_content":"why"}}]}\n\n'
        'data: {"choices":[{"delta":{"content":"ans"}}]}\n\n'
        'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}\n\n'
        "data: [DONE]\n\n"
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=sse_body, headers={"content-type": "text/event-stream"})

    _patch_openai_http(monkeypatch, handler)
    executor = OpenAICompatExecutor(
        base_url="http://127.0.0.1:8000", default_model="qwen3", tier="L4"
    )
    events = [
        event
        async for event in executor.stream(
            InternalRequest(model="qwen3", messages=[Message(role="user", content="hi")])
        )
    ]
    thinking_bits = [
        event["message"].get("thinking")
        for event in events
        if not event["done"] and event["message"].get("thinking")
    ]
    assert thinking_bits == ["why"]
    texts = [event["message"]["content"] for event in events if not event["done"]]
    assert "".join(texts) == "ans"


@pytest.mark.asyncio
async def test_ollama_stream_preserves_thinking_field(monkeypatch):
    lines = [
        json.dumps(
            {
                "message": {"role": "assistant", "content": "", "thinking": "ponder"},
                "done": False,
            }
        ),
        json.dumps({"message": {"role": "assistant", "content": "ok"}, "done": False}),
        json.dumps({"message": {"role": "assistant", "content": ""}, "done": True}),
    ]
    body = "\n".join(lines) + "\n"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=body)

    _patch_router_http(monkeypatch, handler)
    executor = OllamaExecutor(base_url="http://test", default_model="deepseek-r1:8b")
    events = [
        event
        async for event in executor.stream(
            InternalRequest(
                model="deepseek-r1:8b",
                messages=[Message(role="user", content="hi")],
            )
        )
    ]
    assert events[0]["message"]["thinking"] == "ponder"


def test_chat_payload_includes_reasoning_content():
    response = InternalResponse(
        content="answer",
        model="deepseek-r1:8b",
        reasoning_content="secret chain",
        daari_meta=DaariMeta(tier="L3", executor="ollama", latency_ms=1),
    )
    payload = build_chat_completion_payload(
        response, prompt_chars=10, include_daari_meta=False
    )
    message = payload["choices"][0]["message"]
    assert message.get("reasoning_content") == "secret chain"
    assert message["content"] == "answer"


def test_chat_payload_omits_reasoning_when_absent():
    response = InternalResponse(
        content="plain",
        model="llama",
        daari_meta=DaariMeta(tier="L3", executor="ollama", latency_ms=1),
    )
    payload = build_chat_completion_payload(
        response, prompt_chars=5, include_daari_meta=False
    )
    message = payload["choices"][0]["message"]
    assert "reasoning_content" not in message
    assert "reasoning" not in message


def test_responses_emits_reasoning_item_from_local_generation():
    result = InternalResponse(
        content="final",
        model="deepseek-r1:8b",
        reasoning_content="local thoughts",
        daari_meta=DaariMeta(tier="L3", executor="ollama", latency_ms=1),
    )
    items = _output_items_from_result(result)
    assert items[0]["type"] == "reasoning"
    assert items[0]["summary"][0]["text"] == "local thoughts"


def test_anthropic_emits_thinking_block_from_reasoning_content():
    blocks = anthropic_content_with_encrypted_reasoning(
        "visible answer",
        reasoning_content="hidden thoughts",
    )
    assert blocks[0] == {"type": "thinking", "thinking": "hidden thoughts"}
    assert blocks[1] == {"type": "text", "text": "visible answer"}


def test_cache_keeps_reasoning_out_of_content(tmp_path):
    cache = ExactCache(str(tmp_path / "l0"), enabled=True)
    request = InternalRequest(
        model="deepseek-r1:8b",
        messages=[Message(role="user", content="q")],
    )
    response = InternalResponse(
        content="answer only",
        model="deepseek-r1:8b",
        reasoning_content="do not bake into content",
        daari_meta=DaariMeta(tier="L3", executor="ollama", latency_ms=1),
    )
    cache.put(request, response)
    hit = cache.get(request)
    assert hit is not None
    assert hit.content == "answer only"
    assert hit.reasoning_content == "do not bake into content"


@pytest.mark.asyncio
async def test_gateway_chat_surfaces_ollama_thinking(settings, monkeypatch):
    async def fake_execute(request: InternalRequest) -> InternalResponse:
        return InternalResponse(
            content="42",
            model="deepseek-r1:8b",
            reasoning_content="because math",
            daari_meta=DaariMeta(
                tier="L3", executor="ollama", provider_id="ollama", latency_ms=1
            ),
        )

    application = create_app(settings)
    application.state.ctx = AppContext.from_settings(settings)
    monkeypatch.setattr(application.state.ctx.router.ollama, "execute", fake_execute)

    transport = ASGITransport(app=application)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        chat = await client.post(
            "/v1/chat/completions",
            json={
                "model": "deepseek-r1:8b",
                "messages": [{"role": "user", "content": "what?"}],
            },
            headers=META_HEADERS,
        )
        responses = await client.post(
            "/v1/responses",
            json={"model": "deepseek-r1:8b", "input": "what?"},
            headers=META_HEADERS,
        )
        messages = await client.post(
            "/v1/messages",
            json={
                "model": "deepseek-r1:8b",
                "max_tokens": 64,
                "messages": [{"role": "user", "content": "what?"}],
            },
            headers=META_HEADERS,
        )

    assert chat.status_code == 200
    assert chat.json()["choices"][0]["message"]["reasoning_content"] == "because math"
    assert responses.status_code == 200
    out = responses.json()["output"]
    assert out[0]["type"] == "reasoning"
    assert out[0]["summary"][0]["text"] == "because math"
    assert messages.status_code == 200
    content = messages.json()["content"]
    assert content[0]["type"] == "thinking"
    assert content[0]["thinking"] == "because math"
    assert content[1]["type"] == "text"
    assert content[1]["text"] == "42"


@pytest.mark.asyncio
async def test_stream_openai_emits_reasoning_content_delta(settings, monkeypatch):
    async def fake_stream(request: InternalRequest):
        yield {
            "message": {"role": "assistant", "content": "", "thinking": "hmm"},
            "done": False,
        }
        yield {"message": {"role": "assistant", "content": "yes"}, "done": False}
        yield {"message": {"role": "assistant", "content": ""}, "done": True, "done_reason": "stop"}

    application = create_app(settings)
    application.state.ctx = AppContext.from_settings(settings)
    monkeypatch.setattr(application.state.ctx.router.ollama, "stream", fake_stream)
    # Force L3-only path: disable higher local tiers if present.
    router = application.state.ctx.router
    if hasattr(router, "ollama_l4"):
        monkeypatch.setattr(router, "ollama_l4", None, raising=False)
    if hasattr(router, "ollama_l5"):
        monkeypatch.setattr(router, "ollama_l5", None, raising=False)

    transport = ASGITransport(app=application)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/v1/chat/completions",
            json={
                "model": "deepseek-r1:8b",
                "stream": True,
                "messages": [{"role": "user", "content": "hi"}],
            },
            headers=META_HEADERS,
        )
    assert response.status_code == 200
    reasoning_deltas = []
    content_parts = []
    for line in response.text.splitlines():
        if not line.startswith("data: ") or line.strip() == "data: [DONE]":
            continue
        payload = json.loads(line[len("data: ") :])
        choices = payload.get("choices") or []
        if not choices:
            continue
        delta = choices[0].get("delta") or {}
        if delta.get("reasoning_content"):
            reasoning_deltas.append(delta["reasoning_content"])
        if delta.get("content"):
            content_parts.append(delta["content"])
    assert reasoning_deltas == ["hmm"]
    assert "".join(content_parts) == "yes"
