"""OpenAI-compat local executor (vLLM / llama.cpp server / LM Studio) — issue #275."""

from __future__ import annotations

import json

import httpx
import pytest

from daari.gateway.internal import InternalRequest, Message
from daari.router.openai_executor import OpenAICompatExecutor, OpenAICompatRequestError


def _patch_client(monkeypatch, handler) -> None:
    transport = httpx.MockTransport(handler)
    original_client = httpx.AsyncClient

    def patched_client(*args, **kwargs):
        kwargs["transport"] = transport
        return original_client(*args, **kwargs)

    monkeypatch.setattr("daari.router.openai_executor.httpx.AsyncClient", patched_client)


@pytest.mark.asyncio
async def test_execute_posts_chat_completions(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/chat/completions"
        body = json.loads(request.content)
        assert body["model"] == "meta-llama/Llama-3.1-8B"
        assert body["stream"] is False
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {"role": "assistant", "content": "from-vllm"},
                        "finish_reason": "stop",
                    }
                ]
            },
        )

    _patch_client(monkeypatch, handler)
    executor = OpenAICompatExecutor(
        base_url="http://127.0.0.1:8000",
        default_model="meta-llama/Llama-3.1-8B",
        tier="L4",
    )
    response = await executor.execute(
        InternalRequest(model="meta-llama/Llama-3.1-8B", messages=[Message(role="user", content="hi")])
    )
    assert response.content == "from-vllm"
    assert response.daari_meta.executor == "openai"
    assert response.daari_meta.provider_id == "openai:l4"
    assert response.daari_meta.tier == "L4"


@pytest.mark.asyncio
async def test_stream_converts_sse_to_ollama_events(monkeypatch):
    sse_body = (
        'data: {"choices":[{"delta":{"role":"assistant","content":"Hel"}}]}\n\n'
        'data: {"choices":[{"delta":{"content":"lo"}}]}\n\n'
        "data: [DONE]\n\n"
    )

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/chat/completions"
        return httpx.Response(200, text=sse_body, headers={"content-type": "text/event-stream"})

    _patch_client(monkeypatch, handler)
    executor = OpenAICompatExecutor(
        base_url="http://127.0.0.1:8000",
        default_model="meta-llama/Llama-3.1-8B",
        tier="L4",
    )
    events = [
        event
        async for event in executor.stream(
            InternalRequest(model="meta-llama/Llama-3.1-8B", messages=[Message(role="user", content="hi")])
        )
    ]
    texts = [event["message"]["content"] for event in events if not event["done"]]
    assert "".join(texts) == "Hello"
    assert events[-1]["done"] is True


@pytest.mark.asyncio
async def test_execute_error_includes_body(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"error": "no capacity"})

    _patch_client(monkeypatch, handler)
    executor = OpenAICompatExecutor(base_url="http://127.0.0.1:8000", default_model="m")
    with pytest.raises(OpenAICompatRequestError) as excinfo:
        await executor.execute(
            InternalRequest(model="m", messages=[Message(role="user", content="hi")])
        )
    assert excinfo.value.status_code == 503
    assert "no capacity" in str(excinfo.value)
