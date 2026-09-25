"""Idempotency-Key replay on chat, Responses, and modality routes (#714, #1065)."""

from __future__ import annotations

import asyncio
import sqlite3
import time as time_mod
from datetime import datetime, timezone
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from daari.gateway.idempotency import (
    CONFLICT_TYPE,
    assemble_assistant_text_from_sse,
    request_body_hash,
)
from daari.gateway.idempotency_store import IdempotencyStore
from daari.gateway.internal import DaariMeta, InternalRequest, InternalResponse
from daari.gateway.postgres_idempotency import PostgresIdempotencyStore
from daari.observability.retention import prune_all
from daari.router.router import AppContext
from daari.server.app import create_app


def test_request_body_hash_stable_across_key_order():
    a = {"model": "m", "messages": [{"role": "user", "content": "hi"}]}
    b = {"messages": [{"role": "user", "content": "hi"}], "model": "m"}
    assert request_body_hash(a) == request_body_hash(b)


def test_idempotency_store_begin_complete_replay(tmp_path):
    store = IdempotencyStore(tmp_path / "idem.sqlite3", ttl_seconds=60)
    assert store.begin("anonymous", "k1", "hash-a")
    assert not store.begin("anonymous", "k1", "hash-a")
    store.complete(
        "anonymous",
        "k1",
        status_code=200,
        response_body='{"ok":true}',
        media_type="application/json",
    )
    row = store.get("anonymous", "k1")
    assert row is not None
    assert row["state"] == "complete"
    assert row["response_body"] == '{"ok":true}'


def test_idempotency_store_prune(tmp_path):
    store = IdempotencyStore(tmp_path / "idem.sqlite3", ttl_seconds=1)
    assert store.begin("anonymous", "old", "h")
    store.complete(
        "anonymous",
        "old",
        status_code=200,
        response_body="{}",
        media_type="application/json",
    )
    with sqlite3.connect(store.path) as conn:
        conn.execute(
            "UPDATE idempotency SET created_at = 1 WHERE principal = ? AND idem_key = ?",
            ("anonymous", "old"),
        )
    assert store.prune_older_than(10) == 1
    assert store.get("anonymous", "old") is None


def test_postgres_memory_backend_roundtrip():
    store = PostgresIdempotencyStore("memory:idem-test-714", ttl_seconds=60)
    assert store.begin("master", "k", "h1")
    store.complete(
        "master",
        "k",
        status_code=200,
        response_body='{"a":1}',
        media_type="application/json",
        assistant_text="hi",
    )
    row = store.get("master", "k")
    assert row["assistant_text"] == "hi"
    assert store.prune_older_than(0, dry_run=True) == 0


def test_assemble_assistant_text_from_sse():
    sse = (
        'data: {"choices":[{"delta":{"content":"Hel"}}]}\n\n'
        'data: {"choices":[{"delta":{"content":"lo"}}]}\n\n'
        "data: [DONE]\n\n"
    )
    assert assemble_assistant_text_from_sse(sse) == "Hello"


def test_prune_all_sweeps_idempotency(settings, tmp_path):
    settings.trace.path = str(tmp_path / "traces.sqlite3")
    settings.idempotency.ttl_seconds = 60
    store_path = Path(settings.trace.path).expanduser().parent / "idempotency.sqlite3"
    store = IdempotencyStore(store_path, ttl_seconds=60)
    store.begin("anonymous", "old", "h")
    store.complete(
        "anonymous",
        "old",
        status_code=200,
        response_body="{}",
        media_type="application/json",
    )
    with sqlite3.connect(store_path) as conn:
        conn.execute(
            "UPDATE idempotency SET created_at = ? WHERE principal = ?",
            (int(time_mod.time()) - 10_000, "anonymous"),
        )
    results = prune_all(settings, now=datetime.now(timezone.utc), dry_run=False)
    idem = next(r for r in results if r.store == "idempotency")
    assert idem.deleted == 1
    assert store.get("anonymous", "old") is None


@pytest.mark.asyncio
async def test_chat_idempotency_replays_without_second_route(settings, monkeypatch, tmp_path):
    settings.trace.path = str(tmp_path / "traces.sqlite3")
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    calls = {"n": 0}

    async def fake_route(request: InternalRequest) -> InternalResponse:
        calls["n"] += 1
        return InternalResponse(
            content=f"answer-{calls['n']}",
            model="llama3.2:3b",
            daari_meta=DaariMeta(tier="L3", executor="ollama", provider_id="ollama"),
        )

    monkeypatch.setattr(app.state.ctx.router, "route", fake_route)
    body = {
        "model": "llama3.2:3b",
        "messages": [{"role": "user", "content": "hi"}],
    }
    headers = {"Idempotency-Key": "chat-key-1"}
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        first = await client.post("/v1/chat/completions", json=body, headers=headers)
        second = await client.post("/v1/chat/completions", json=body, headers=headers)
    assert first.status_code == 200
    assert second.status_code == 200
    assert first.content == second.content
    assert calls["n"] == 1
    assert first.json()["choices"][0]["message"]["content"] == "answer-1"


@pytest.mark.asyncio
async def test_chat_idempotency_conflict_on_body_mismatch(settings, monkeypatch, tmp_path):
    settings.trace.path = str(tmp_path / "traces.sqlite3")
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)

    async def fake_route(request: InternalRequest) -> InternalResponse:
        return InternalResponse(
            content="ok",
            model="llama3.2:3b",
            daari_meta=DaariMeta(tier="L3", executor="ollama", provider_id="ollama"),
        )

    monkeypatch.setattr(app.state.ctx.router, "route", fake_route)
    headers = {"Idempotency-Key": "chat-conflict"}
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        first = await client.post(
            "/v1/chat/completions",
            json={
                "model": "llama3.2:3b",
                "messages": [{"role": "user", "content": "one"}],
            },
            headers=headers,
        )
        second = await client.post(
            "/v1/chat/completions",
            json={
                "model": "llama3.2:3b",
                "messages": [{"role": "user", "content": "two"}],
            },
            headers=headers,
        )
    assert first.status_code == 200
    assert second.status_code == 409
    assert second.json()["error"]["type"] == CONFLICT_TYPE


@pytest.mark.asyncio
async def test_chat_idempotency_inflight_waits(settings, monkeypatch, tmp_path):
    settings.trace.path = str(tmp_path / "traces.sqlite3")
    settings.idempotency.wait_seconds = 5.0
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    started = asyncio.Event()
    release = asyncio.Event()
    calls = {"n": 0}

    async def fake_route(request: InternalRequest) -> InternalResponse:
        calls["n"] += 1
        started.set()
        await release.wait()
        return InternalResponse(
            content="slow",
            model="llama3.2:3b",
            daari_meta=DaariMeta(tier="L3", executor="ollama", provider_id="ollama"),
        )

    monkeypatch.setattr(app.state.ctx.router, "route", fake_route)
    body = {
        "model": "llama3.2:3b",
        "messages": [{"role": "user", "content": "hi"}],
    }
    headers = {"Idempotency-Key": "inflight-1"}
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:

        async def first():
            return await client.post("/v1/chat/completions", json=body, headers=headers)

        async def second():
            await started.wait()
            return await client.post("/v1/chat/completions", json=body, headers=headers)

        t1 = asyncio.create_task(first())
        t2 = asyncio.create_task(second())
        await started.wait()
        await asyncio.sleep(0.05)
        release.set()
        r1, r2 = await asyncio.gather(t1, t2)

    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r1.content == r2.content
    assert calls["n"] == 1


@pytest.mark.asyncio
async def test_chat_stream_idempotency_replays_text(settings, monkeypatch, tmp_path):
    settings.trace.path = str(tmp_path / "traces.sqlite3")
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    calls = {"n": 0}

    async def fake_stream(request: InternalRequest, outcome=None):
        calls["n"] += 1
        yield 'data: {"choices":[{"delta":{"content":"Hi"}}]}\n\n'
        yield "data: [DONE]\n\n"

    monkeypatch.setattr(app.state.ctx.router, "stream_openai_chunks", fake_stream)
    monkeypatch.setattr(app.state.ctx.router, "ensure_capable", lambda _req: None)
    body = {
        "model": "llama3.2:3b",
        "messages": [{"role": "user", "content": "hi"}],
        "stream": True,
    }
    headers = {"Idempotency-Key": "stream-key"}
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        first = await client.post("/v1/chat/completions", json=body, headers=headers)
        second = await client.post("/v1/chat/completions", json=body, headers=headers)
    assert first.status_code == 200
    assert second.status_code == 200
    assert assemble_assistant_text_from_sse(first.text) == "Hi"
    assert assemble_assistant_text_from_sse(second.text) == "Hi"
    assert calls["n"] == 1


@pytest.mark.asyncio
async def test_responses_idempotency_replays(settings, monkeypatch, tmp_path):
    settings.trace.path = str(tmp_path / "traces.sqlite3")
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    calls = {"n": 0}

    async def fake_route(request: InternalRequest) -> InternalResponse:
        calls["n"] += 1
        return InternalResponse(
            content=f"resp-{calls['n']}",
            model="llama3.2:3b",
            daari_meta=DaariMeta(tier="L3", executor="ollama", provider_id="ollama"),
        )

    monkeypatch.setattr(app.state.ctx.router, "route", fake_route)
    body = {"model": "llama3.2:3b", "input": "hello", "store": False}
    headers = {"Idempotency-Key": "resp-key"}
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        first = await client.post("/v1/responses", json=body, headers=headers)
        second = await client.post("/v1/responses", json=body, headers=headers)
    assert first.status_code == 200
    assert second.status_code == 200
    assert first.content == second.content
    assert calls["n"] == 1


@pytest.mark.asyncio
async def test_missing_idempotency_key_is_noop(settings, monkeypatch, tmp_path):
    settings.trace.path = str(tmp_path / "traces.sqlite3")
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    calls = {"n": 0}

    async def fake_route(request: InternalRequest) -> InternalResponse:
        calls["n"] += 1
        return InternalResponse(
            content=f"n{calls['n']}",
            model="llama3.2:3b",
            daari_meta=DaariMeta(tier="L3", executor="ollama", provider_id="ollama"),
        )

    monkeypatch.setattr(app.state.ctx.router, "route", fake_route)
    body = {
        "model": "llama3.2:3b",
        "messages": [{"role": "user", "content": "hi"}],
    }
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post("/v1/chat/completions", json=body)
        await client.post("/v1/chat/completions", json=body)
    assert calls["n"] == 2


# --- modality routes (#1065) -------------------------------------------------


class _RecordingEmbedder:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def embed(self, text: str, *, model: str | None = None) -> list[float]:
        self.calls.append(text)
        return [0.1, 0.2, 0.3]

    async def embed_many(
        self, texts: list[str], *, model: str | None = None
    ) -> list[list[float] | None]:
        return [await self.embed(text, model=model) for text in texts]


@pytest.mark.asyncio
async def test_embeddings_idempotency_replays_without_second_embed(
    settings, tmp_path
):
    settings.trace.path = str(tmp_path / "traces.sqlite3")
    settings.cache.l1.enabled = True
    embedder = _RecordingEmbedder()
    app = create_app(settings)
    ctx = AppContext.from_settings(settings)
    ctx.router.semantic_cache.embedder = embedder
    app.state.ctx = ctx
    body = {"model": "nomic-embed-text", "input": "hello"}
    headers = {"Idempotency-Key": "embed-key-1"}
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        first = await client.post("/v1/embeddings", json=body, headers=headers)
        second = await client.post("/v1/embeddings", json=body, headers=headers)
    assert first.status_code == 200
    assert second.status_code == 200
    assert first.content == second.content
    assert embedder.calls == ["hello"]


@pytest.mark.asyncio
async def test_embeddings_idempotency_conflict_on_body_mismatch(settings, tmp_path):
    settings.trace.path = str(tmp_path / "traces.sqlite3")
    settings.cache.l1.enabled = True
    embedder = _RecordingEmbedder()
    app = create_app(settings)
    ctx = AppContext.from_settings(settings)
    ctx.router.semantic_cache.embedder = embedder
    app.state.ctx = ctx
    headers = {"Idempotency-Key": "embed-conflict"}
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        first = await client.post(
            "/v1/embeddings",
            json={"model": "nomic-embed-text", "input": "one"},
            headers=headers,
        )
        second = await client.post(
            "/v1/embeddings",
            json={"model": "nomic-embed-text", "input": "two"},
            headers=headers,
        )
    assert first.status_code == 200
    assert second.status_code == 409
    assert second.json()["error"]["type"] == CONFLICT_TYPE


@pytest.mark.asyncio
async def test_embeddings_missing_idempotency_key_is_noop(settings, tmp_path):
    settings.trace.path = str(tmp_path / "traces.sqlite3")
    settings.cache.l1.enabled = True
    # Disable L0 so identical inputs still call the embedder twice.
    settings.cache.l0.enabled = False
    embedder = _RecordingEmbedder()
    app = create_app(settings)
    ctx = AppContext.from_settings(settings)
    ctx.router.semantic_cache.embedder = embedder
    app.state.ctx = ctx
    body = {"model": "nomic-embed-text", "input": "hello"}
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post("/v1/embeddings", json=body)
        await client.post("/v1/embeddings", json=body)
    assert len(embedder.calls) == 2


def _patch_httpx(monkeypatch, module_path: str, handler):
    import httpx

    mod = __import__(module_path, fromlist=["_http"])
    mod._http = None
    real = httpx.AsyncClient

    class Patched(real):
        def __init__(self, *args, **kwargs):
            if kwargs.get("transport") is None:
                kwargs["transport"] = httpx.MockTransport(handler)
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", Patched)
    monkeypatch.setattr(f"{module_path}.httpx.AsyncClient", Patched)


@pytest.mark.asyncio
async def test_moderations_idempotency_replays_without_second_upstream(
    settings, monkeypatch, tmp_path
):
    import httpx
    from daari.config.settings import FrontierProviderConfig

    settings.trace.path = str(tmp_path / "traces.sqlite3")
    seen: list[httpx.Request] = []
    payload = {
        "id": "modr-idem",
        "model": "omni-moderation-latest",
        "results": [{"flagged": False, "categories": {}, "category_scores": {}}],
    }

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=payload)

    _patch_httpx(monkeypatch, "daari.gateway.moderations", handler)
    settings.frontier.enabled = True
    settings.frontier.providers = [
        FrontierProviderConfig(
            id="openai",
            base_url="https://api.openai.com/v1",
            model="gpt-4o",
            keys=["sk-test"],
        )
    ]
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    body = {"input": "hello", "model": "omni-moderation-latest"}
    headers = {"Idempotency-Key": "mod-key-1"}
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        first = await client.post("/v1/moderations", json=body, headers=headers)
        second = await client.post("/v1/moderations", json=body, headers=headers)
    assert first.status_code == 200
    assert second.status_code == 200
    assert first.content == second.content
    assert len(seen) == 1


@pytest.mark.asyncio
async def test_speech_idempotency_replays_binary_without_second_upstream(
    settings, monkeypatch, tmp_path
):
    import httpx

    settings.trace.path = str(tmp_path / "traces.sqlite3")
    audio = b"ID3fake-mp3-bytes"
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, content=audio, headers={"content-type": "audio/mpeg"})

    _patch_httpx(monkeypatch, "daari.gateway.speech", handler)
    settings.tts.base_url = "http://tts.local/v1/"
    settings.tts.model = "tts-1"
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    body = {
        "model": "tts-1",
        "input": "Hello from daari",
        "voice": "alloy",
        "response_format": "mp3",
    }
    headers = {"Idempotency-Key": "tts-key-1"}
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        first = await client.post("/v1/audio/speech", json=body, headers=headers)
        second = await client.post("/v1/audio/speech", json=body, headers=headers)
    assert first.status_code == 200
    assert second.status_code == 200
    assert first.content == audio
    assert second.content == audio
    assert first.content == second.content
    assert len(seen) == 1


@pytest.mark.asyncio
async def test_transcriptions_idempotency_honors_multipart_digest(
    settings, monkeypatch, tmp_path
):
    import httpx

    settings.trace.path = str(tmp_path / "traces.sqlite3")
    audio = b"RIFF-audio-bytes"
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"text": "hello from asr"})

    _patch_httpx(monkeypatch, "daari.gateway.transcriptions", handler)
    settings.asr.base_url = "http://asr.local/v1/"
    settings.asr.model = "whisper-1"
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    headers = {"Idempotency-Key": "asr-key-1"}
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        first = await client.post(
            "/v1/audio/transcriptions",
            files={"file": ("note.wav", audio, "audio/wav")},
            data={"model": "whisper-1", "response_format": "json"},
            headers=headers,
        )
        second = await client.post(
            "/v1/audio/transcriptions",
            files={"file": ("note.wav", audio, "audio/wav")},
            data={"model": "whisper-1", "response_format": "json"},
            headers=headers,
        )
        conflict = await client.post(
            "/v1/audio/transcriptions",
            files={"file": ("note.wav", audio + b"-other", "audio/wav")},
            data={"model": "whisper-1", "response_format": "json"},
            headers=headers,
        )
    assert first.status_code == 200
    assert second.status_code == 200
    assert first.content == second.content
    assert len(seen) == 1
    assert conflict.status_code == 409
    assert conflict.json()["error"]["type"] == CONFLICT_TYPE


def test_multipart_body_hash_stable():
    from daari.gateway.idempotency import multipart_body_hash

    a = multipart_body_hash(
        fields={"model": "whisper-1", "language": "en"},
        file_bytes=b"RIFF",
        filename="a.wav",
    )
    b = multipart_body_hash(
        fields={"language": "en", "model": "whisper-1"},
        file_bytes=b"RIFF",
        filename="a.wav",
    )
    c = multipart_body_hash(
        fields={"model": "whisper-1", "language": "en"},
        file_bytes=b"RIFF-diff",
        filename="a.wav",
    )
    assert a == b
    assert a != c
