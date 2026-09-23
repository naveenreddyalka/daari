"""ASR / TTS / embed HTTP retries via RetryPolicy (#980)."""

from __future__ import annotations

import httpx
import pytest
from httpx import ASGITransport, AsyncClient

from daari.cache.semantic import OllamaEmbedder
from daari.router.retry import RetryPolicy
from daari.router.router import AppContext
from daari.server.app import create_app


def _fast_retry(settings) -> None:
    settings.upstream.retry.attempts = 3
    settings.upstream.retry.base_delay_ms = 0
    settings.upstream.retry.max_delay_ms = 0
    settings.upstream.retry.jitter = 0.0


def _sequence_handler(responses: list, seen: list[httpx.Request]):
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        item = responses[min(len(seen) - 1, len(responses) - 1)]
        if isinstance(item, Exception):
            raise item
        status, payload = item
        if isinstance(payload, (bytes, bytearray)):
            return httpx.Response(status, content=payload)
        return httpx.Response(status, json=payload)

    return handler


def _patch_transcriptions(monkeypatch, handler):
    from daari.gateway import transcriptions

    transcriptions._http = None
    real = httpx.AsyncClient

    class Patched(real):
        def __init__(self, *args, **kwargs):
            if kwargs.get("transport") is None:
                kwargs["transport"] = httpx.MockTransport(handler)
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", Patched)
    monkeypatch.setattr("daari.gateway.transcriptions.httpx.AsyncClient", Patched)


@pytest.mark.asyncio
async def test_asr_retries_503_then_succeeds(settings, monkeypatch):
    _fast_retry(settings)
    settings.asr.base_url = "http://asr.local/v1"
    settings.asr.model = "whisper-1"
    seen: list[httpx.Request] = []
    _patch_transcriptions(
        monkeypatch,
        _sequence_handler([(503, {"error": "busy"}), (200, {"text": "ok"})], seen),
    )
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/audio/transcriptions",
            data={"model": "whisper-1", "response_format": "json"},
            files={"file": ("a.wav", b"RIFF", "audio/wav")},
        )
    assert response.status_code == 200, response.text
    assert response.json()["text"] == "ok"
    assert len(seen) == 2


@pytest.mark.asyncio
async def test_asr_4xx_does_not_retry(settings, monkeypatch):
    _fast_retry(settings)
    settings.asr.base_url = "http://asr.local/v1"
    settings.asr.model = "whisper-1"
    seen: list[httpx.Request] = []
    _patch_transcriptions(
        monkeypatch,
        _sequence_handler([(400, {"error": "bad"})], seen),
    )
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/audio/transcriptions",
            data={"model": "whisper-1", "response_format": "json"},
            files={"file": ("a.wav", b"RIFF", "audio/wav")},
        )
    assert response.status_code == 502
    assert len(seen) == 1


@pytest.mark.asyncio
async def test_embed_retries_503_then_succeeds(settings, monkeypatch):
    _fast_retry(settings)
    seen: list[httpx.Request] = []
    transport = httpx.MockTransport(
        _sequence_handler(
            [
                (503, {"error": "busy"}),
                (200, {"embeddings": [[0.1, 0.2, 0.3]]}),
            ],
            seen,
        )
    )
    embedder = OllamaEmbedder(
        "http://ollama.local",
        "nomic-embed-text",
        transport=transport,
        retry=RetryPolicy.from_settings(settings.upstream.retry),
    )
    vectors = await embedder.embed_many(["hello"])
    assert vectors == [[0.1, 0.2, 0.3]]
    assert len(seen) == 2
