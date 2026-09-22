"""Pooled httpx.AsyncClient reuse across upstream hops (#971)."""

from __future__ import annotations

import json

import httpx
import pytest

from daari.cache.semantic import OllamaEmbedder
from daari.config.settings import Settings
from daari.gateway.internal import InternalRequest, Message
from daari.gateway import speech, transcriptions
from daari.router.frontier import FrontierExecutor
from daari.router.http_pool import PoolLimits, pool_limits_from_settings
from daari.router.mlx_executor import MLXExecutor
from daari.router.openai_executor import OpenAICompatExecutor
from daari.router.router import OllamaExecutor


def _patch(monkeypatch, module_path: str, handler):
    transport = httpx.MockTransport(handler)
    constructed: list[httpx.AsyncClient] = []
    original = httpx.AsyncClient

    def patched(*args, **kwargs):
        kwargs["transport"] = transport
        client = original(*args, **kwargs)
        constructed.append(client)
        return client

    monkeypatch.setattr(f"{module_path}.httpx.AsyncClient", patched)
    return constructed


def _req(model: str = "m") -> InternalRequest:
    return InternalRequest(model=model, messages=[Message(role="user", content="hi")])


def test_pool_limits_from_settings_defaults():
    limits = pool_limits_from_settings(Settings())
    assert limits.max_connections == 100
    assert limits.max_keepalive_connections == 20


def test_pool_limits_from_settings_override():
    settings = Settings()
    settings.upstream.pool_max_connections = 40
    settings.upstream.pool_keepalive_connections = 8
    limits = pool_limits_from_settings(settings)
    assert limits == PoolLimits(max_connections=40, max_keepalive_connections=8)


@pytest.mark.asyncio
async def test_ollama_reuses_client(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"message": {"role": "assistant", "content": "ok"}, "done": True}
        )

    constructed = _patch(monkeypatch, "daari.router.router", handler)
    executor = OllamaExecutor(base_url="http://ollama.test", default_model="m")
    await executor.execute(_req())
    await executor.execute(_req())
    assert len(constructed) == 1
    assert constructed[0] is executor._client()
    await executor.aclose()
    assert constructed[0].is_closed


@pytest.mark.asyncio
async def test_ollama_sequential_streams_reuse_client(monkeypatch):
    sse = json.dumps({"message": {"role": "assistant", "content": "x"}, "done": True})

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=sse + "\n", headers={"content-type": "application/x-ndjson"})

    constructed = _patch(monkeypatch, "daari.router.router", handler)
    executor = OllamaExecutor(base_url="http://ollama.test", default_model="m")
    for _ in range(2):
        events = [e async for e in executor.stream(_req())]
        assert events
    assert len(constructed) == 1
    await executor.aclose()


@pytest.mark.asyncio
async def test_openai_compat_reuses_client(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"choices": [{"message": {"role": "assistant", "content": "ok"}, "finish_reason": "stop"}]},
        )

    constructed = _patch(monkeypatch, "daari.router.openai_executor", handler)
    executor = OpenAICompatExecutor(base_url="http://vllm.test", default_model="m")
    await executor.execute(_req())
    await executor.execute(_req())
    assert len(constructed) == 1
    await executor.aclose()


@pytest.mark.asyncio
async def test_openai_compat_sequential_streams_reuse_client(monkeypatch):
    sse = (
        'data: {"choices":[{"delta":{"content":"a"}}]}\n\n'
        "data: [DONE]\n\n"
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=sse, headers={"content-type": "text/event-stream"})

    constructed = _patch(monkeypatch, "daari.router.openai_executor", handler)
    executor = OpenAICompatExecutor(base_url="http://vllm.test", default_model="m")
    for _ in range(2):
        events = [e async for e in executor.stream(_req())]
        assert events[-1]["done"] is True
    assert len(constructed) == 1
    await executor.aclose()


@pytest.mark.asyncio
async def test_mlx_reuses_client(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"choices": [{"message": {"role": "assistant", "content": "ok"}, "finish_reason": "stop"}]},
        )

    constructed = _patch(monkeypatch, "daari.router.mlx_executor", handler)
    executor = MLXExecutor(base_url="http://mlx.test", default_model="m")
    await executor.execute(_req())
    await executor.execute(_req())
    assert len(constructed) == 1
    await executor.aclose()


@pytest.mark.asyncio
async def test_frontier_reuses_client(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"choices": [{"message": {"role": "assistant", "content": "ok"}}]},
        )

    constructed = _patch(monkeypatch, "daari.router.frontier", handler)
    executor = FrontierExecutor(
        base_url="https://api.openai.com/v1",
        default_model="gpt-4o-mini",
        api_key="sk-test",
    )
    await executor.execute(_req("gpt-4o-mini"), escalated_from="L5", local_confidence=0.1)
    await executor.execute(_req("gpt-4o-mini"), escalated_from="L5", local_confidence=0.1)
    assert len(constructed) == 1
    await executor.aclose()


@pytest.mark.asyncio
async def test_embedder_reuses_client(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        if request.url.path.endswith("/api/embed"):
            texts = body.get("input") or []
            return httpx.Response(
                200, json={"embeddings": [[0.1, 0.2] for _ in texts]}
            )
        return httpx.Response(200, json={"embedding": [0.1, 0.2]})

    constructed = _patch(monkeypatch, "daari.cache.semantic", handler)
    embedder = OllamaEmbedder("http://ollama.test", "nomic-embed-text", cache_size=0)
    assert await embedder.embed("a") is not None
    assert await embedder.embed("b") is not None
    assert len(constructed) == 1
    await embedder.aclose()


@pytest.mark.asyncio
async def test_speech_reuses_client(monkeypatch):
    speech._http = None
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, content=b"audio")

    constructed = _patch(monkeypatch, "daari.gateway.speech", handler)
    await speech.post_speech(
        "http://tts.test/v1/audio/speech",
        headers={},
        payload={"input": "hi"},
        timeout=5.0,
    )
    await speech.post_speech(
        "http://tts.test/v1/audio/speech",
        headers={},
        payload={"input": "hi"},
        timeout=5.0,
    )
    assert len(constructed) == 1
    assert len(seen) == 2
    await speech.aclose_http()


@pytest.mark.asyncio
async def test_transcriptions_reuses_client(monkeypatch):
    transcriptions._http = None
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"text": "hi"})

    constructed = _patch(monkeypatch, "daari.gateway.transcriptions", handler)
    await transcriptions.post_transcription(
        "http://asr.test/v1/audio/transcriptions",
        headers={},
        filename="a.wav",
        content=b"bytes",
        content_type="audio/wav",
        form={"model": "whisper"},
        timeout=5.0,
    )
    await transcriptions.post_transcription(
        "http://asr.test/v1/audio/transcriptions",
        headers={},
        filename="a.wav",
        content=b"bytes",
        content_type="audio/wav",
        form={"model": "whisper"},
        timeout=5.0,
    )
    assert len(constructed) == 1
    assert len(seen) == 2
    await transcriptions.aclose_http()


@pytest.mark.asyncio
async def test_per_request_timeout_passed_not_baked_into_client(monkeypatch):
    seen_timeouts: list[object] = []

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"message": {"role": "assistant", "content": "ok"}, "done": True}
        )

    transport = httpx.MockTransport(handler)
    original = httpx.AsyncClient
    client_timeouts: list[object] = []

    def patched(*args, **kwargs):
        client_timeouts.append(kwargs.get("timeout"))
        kwargs["transport"] = transport
        client = original(*args, **kwargs)
        real_post = client.post

        async def tracking_post(*a, **kw):
            seen_timeouts.append(kw.get("timeout"))
            return await real_post(*a, **kw)

        client.post = tracking_post  # type: ignore[method-assign]
        return client

    monkeypatch.setattr("daari.router.router.httpx.AsyncClient", patched)
    executor = OllamaExecutor(base_url="http://ollama.test", default_model="m", timeout=33.0)
    await executor.execute(_req())
    assert client_timeouts == [None]
    assert seen_timeouts and seen_timeouts[0] == 33.0
    await executor.aclose()
