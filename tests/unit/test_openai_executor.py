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


async def _stream_events(monkeypatch, sse_body: str, seen: dict | None = None) -> list[dict]:
    def handler(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen["body"] = json.loads(request.content)
        return httpx.Response(200, text=sse_body, headers={"content-type": "text/event-stream"})

    _patch_client(monkeypatch, handler)
    executor = OpenAICompatExecutor(
        base_url="http://127.0.0.1:8000", default_model="meta-llama/Llama-3.1-8B", tier="L4"
    )
    return [
        event
        async for event in executor.stream(
            InternalRequest(model="meta-llama/Llama-3.1-8B", messages=[Message(role="user", content="hi")])
        )
    ]


@pytest.mark.asyncio
async def test_stream_requests_usage_and_surfaces_final_usage_chunk(monkeypatch):
    """vLLM-style: one usage-only chunk (empty choices) right before [DONE] (#320)."""
    sse_body = (
        'data: {"choices":[{"delta":{"role":"assistant","content":"Hel"}}]}\n\n'
        'data: {"choices":[{"delta":{"content":"lo"}}]}\n\n'
        'data: {"choices":[],"usage":{"prompt_tokens":11,"completion_tokens":7,"total_tokens":18}}\n\n'
        "data: [DONE]\n\n"
    )
    seen: dict = {}
    events = await _stream_events(monkeypatch, sse_body, seen)

    assert seen["body"]["stream_options"] == {"include_usage": True}
    reported = [e for e in events if e.get("prompt_eval_count") is not None]
    assert len(reported) == 1
    assert (reported[0]["prompt_eval_count"], reported[0]["eval_count"]) == (11, 7)
    assert reported[0]["message"]["content"] == ""
    assert "".join(e["message"]["content"] for e in events) == "Hello"


@pytest.mark.asyncio
async def test_stream_running_usage_totals_pass_through_unsummed(monkeypatch):
    """Backends that attach cumulative usage to every chunk: each event carries
    the provider's figure verbatim so the consumer can keep the last one."""
    sse_body = (
        'data: {"choices":[{"delta":{"content":"a"}}],"usage":{"prompt_tokens":11,"completion_tokens":1}}\n\n'
        'data: {"choices":[{"delta":{"content":"b"}}],"usage":{"prompt_tokens":11,"completion_tokens":2}}\n\n'
        'data: {"choices":[{"delta":{"content":"c"}}],"usage":{"prompt_tokens":11,"completion_tokens":3}}\n\n'
        "data: [DONE]\n\n"
    )
    events = await _stream_events(monkeypatch, sse_body)

    counts = [e["eval_count"] for e in events if e.get("eval_count") is not None]
    assert counts == [1, 2, 3]
    assert all(e["prompt_eval_count"] == 11 for e in events if "prompt_eval_count" in e)


@pytest.mark.asyncio
async def test_non_stream_payload_has_no_stream_options(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert "stream_options" not in body
        return httpx.Response(
            200, json={"choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}]}
        )

    _patch_client(monkeypatch, handler)
    executor = OpenAICompatExecutor(
        base_url="http://127.0.0.1:8000", default_model="meta-llama/Llama-3.1-8B", tier="L4"
    )
    response = await executor.execute(
        InternalRequest(model="meta-llama/Llama-3.1-8B", messages=[Message(role="user", content="hi")])
    )
    assert response.content == "ok"


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
