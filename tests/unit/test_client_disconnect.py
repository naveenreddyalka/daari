"""Cancel upstream work when the client disconnects (#769)."""

from __future__ import annotations

import asyncio
import json

import pytest
from httpx import ASGITransport, AsyncClient
from starlette.requests import Request

from daari.gateway.internal import DaariMeta, InternalRequest, InternalResponse
from daari.gateway.streaming import stream_with_keepalive
from daari.observability.metrics import Metrics
from daari.observability.prometheus import render_prometheus
from daari.router.router import AppContext
from daari.server.app import create_app
from tests.conftest import mock_all_ollama_executors

CHAT = {
    "model": "daari",
    "messages": [{"role": "user", "content": "disconnect probe please"}],
}
NO_CACHE = {"X-Daari-No-Cache": "true"}


class _Ledger:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def record(self, **kwargs: object) -> None:
        self.calls.append(kwargs)


def _app(settings):
    application = create_app(settings)
    application.state.ctx = AppContext.from_settings(settings)
    return application


def _hanging_execute(started: asyncio.Event, cancelled: asyncio.Event):
    async def execute(request: InternalRequest) -> InternalResponse:
        started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            cancelled.set()
            raise
        return InternalResponse(
            content="should-not-return",
            model="llama3.2:3b",
            daari_meta=DaariMeta(tier="L3", executor="ollama", latency_ms=1),
        )

    return execute


async def _fast_execute(request: InternalRequest) -> InternalResponse:
    return InternalResponse(
        content="ok",
        model="llama3.2:3b",
        daari_meta=DaariMeta(tier="L3", executor="ollama", latency_ms=1),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("path", "payload", "headers", "phase"),
    [
        ("/v1/chat/completions", CHAT, NO_CACHE, "chat"),
        (
            "/v1/messages",
            {"model": "daari", "max_tokens": 16, "messages": CHAT["messages"]},
            NO_CACHE,
            "anthropic",
        ),
        ("/v1/responses", {"model": "daari", "input": "disconnect probe please"}, NO_CACHE, "responses"),
        (
            "/api/chat",
            {"model": "daari", "stream": False, "messages": CHAT["messages"]},
            NO_CACHE,
            "chat",
        ),
        (
            "/api/generate",
            {"model": "daari", "stream": False, "prompt": "disconnect probe please"},
            NO_CACHE,
            "chat",
        ),
    ],
)
async def test_nonstream_disconnect_cancels_executor(
    settings, monkeypatch, path, payload, headers, phase
):
    app = _app(settings)
    started = asyncio.Event()
    cancelled = asyncio.Event()
    mock_all_ollama_executors(monkeypatch, app.state.ctx.router, _hanging_execute(started, cancelled))

    async def is_disconnected(self: Request) -> bool:
        return started.is_set()

    monkeypatch.setattr(Request, "is_disconnected", is_disconnected)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(path, json=payload, headers=headers)

    assert cancelled.is_set()
    assert response.status_code == 499
    text = render_prometheus(app.state.ctx.metrics)
    assert f'daari_cancelled_requests_total{{phase="{phase}"}} 1' in text


@pytest.mark.asyncio
async def test_cancelled_nonstream_does_not_double_count_ledger(settings, monkeypatch):
    app = _app(settings)
    ledger = _Ledger()
    app.state.ctx.router.usage_ledger = ledger
    started = asyncio.Event()
    cancelled = asyncio.Event()
    mock_all_ollama_executors(monkeypatch, app.state.ctx.router, _hanging_execute(started, cancelled))

    async def is_disconnected(self: Request) -> bool:
        return started.is_set()

    monkeypatch.setattr(Request, "is_disconnected", is_disconnected)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/v1/chat/completions", json=CHAT, headers=NO_CACHE)
    assert response.status_code == 499
    assert cancelled.is_set()
    assert len(ledger.calls) <= 1
    cancelled_rows = len(ledger.calls)

    monkeypatch.undo()
    mock_all_ollama_executors(monkeypatch, app.state.ctx.router, _fast_execute)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/v1/chat/completions", json=CHAT, headers=NO_CACHE)
    assert response.status_code == 200
    assert len(ledger.calls) == cancelled_rows + 1


@pytest.mark.asyncio
async def test_normal_chat_completion_is_unchanged(settings, monkeypatch):
    app = _app(settings)
    mock_all_ollama_executors(monkeypatch, app.state.ctx.router, _fast_execute)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/v1/chat/completions", json=CHAT, headers=NO_CACHE)
    assert response.status_code == 200
    assert response.json()["choices"][0]["message"]["content"] == "ok"
    assert "daari_cancelled_requests_total" not in render_prometheus(app.state.ctx.metrics)


@pytest.mark.asyncio
async def test_stream_aclose_stops_upstream_and_records_cancel():
    consumed: list[object] = []
    notes: list[str] = []

    async def source():
        try:
            for i in range(20):
                consumed.append(i)
                yield str(i)
                await asyncio.sleep(0)
        finally:
            consumed.append("closed")

    gen = stream_with_keepalive(
        source(),
        interval_seconds=0,
        on_cancel=lambda: notes.append("cancel"),
    )
    assert await gen.__anext__() == "0"
    await gen.aclose()
    assert "closed" in consumed
    assert notes == ["cancel"]
    assert 19 not in consumed

    metrics = Metrics()
    metrics.record_cancelled("stream")
    text = render_prometheus(metrics)
    assert 'daari_cancelled_requests_total{phase="stream"} 1' in text


@pytest.mark.asyncio
async def test_embeddings_disconnect_cancels_embedder(settings, monkeypatch):
    app = _app(settings)
    settings.cache.l1.enabled = True
    started = asyncio.Event()
    cancelled = asyncio.Event()

    class HangingEmbedder:
        model = "nomic-embed-text"

        async def embed(self, text: str, *, model: str | None = None):
            return (await self.embed_many([text], model=model))[0]

        async def embed_many(self, texts: list[str], *, model: str | None = None):
            started.set()
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                cancelled.set()
                raise
            return [[0.1] for _ in texts]

    app.state.ctx.router.semantic_cache.embedder = HangingEmbedder()

    async def is_disconnected(self: Request) -> bool:
        return started.is_set()

    monkeypatch.setattr(Request, "is_disconnected", is_disconnected)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/embeddings",
            json={"model": "nomic-embed-text", "input": "hang"},
        )
    assert cancelled.is_set()
    assert response.status_code == 499
    assert 'daari_cancelled_requests_total{phase="embed"} 1' in render_prometheus(
        app.state.ctx.metrics
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("path", "phase"),
    [
        ("/v1/audio/transcriptions", "asr"),
        ("/v1/audio/translations", "translation"),
    ],
)
async def test_asr_disconnect_cancels_upstream(settings, monkeypatch, path, phase):
    import httpx

    from daari.gateway import transcriptions as transcriptions_mod

    app = _app(settings)
    settings.asr.base_url = "http://asr.local/v1"
    started = asyncio.Event()
    cancelled = asyncio.Event()

    async def hanging_post(*args, **kwargs):
        started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            cancelled.set()
            raise
        return httpx.Response(200, json={"text": "should-not"})

    monkeypatch.setattr(transcriptions_mod, "post_transcription", hanging_post)

    async def is_disconnected(self: Request) -> bool:
        return started.is_set()

    monkeypatch.setattr(Request, "is_disconnected", is_disconnected)
    files = {"file": ("note.wav", b"RIFF", "audio/wav")}
    data = {"model": "whisper-1", "response_format": "json"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(path, files=files, data=data)
    assert cancelled.is_set()
    assert response.status_code == 499
    assert f'daari_cancelled_requests_total{{phase="{phase}"}} 1' in render_prometheus(
        app.state.ctx.metrics
    )


@pytest.mark.asyncio
async def test_client_stream_close_stops_fake_upstream(settings, monkeypatch):
    """Closing the response stream mid-generation stops the fake upstream."""
    app = _app(settings)
    consumed: list[int] = []
    release = asyncio.Event()

    class FakeStream:
        default_model = "llama3.2:3b"

        async def stream(self, request: InternalRequest):
            for i in range(8):
                consumed.append(i)
                yield {"message": {"role": "assistant", "content": "x"}, "done": False}
                await release.wait()

    monkeypatch.setattr(app.state.ctx.router, "_executor_for_tier", lambda tier: FakeStream())
    body = json.dumps({**CHAT, "stream": True}).encode()
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": "/v1/chat/completions",
        "raw_path": b"/v1/chat/completions",
        "query_string": b"",
        "headers": [
            (b"content-type", b"application/json"),
            (b"content-length", str(len(body)).encode()),
            (b"x-daari-no-cache", b"true"),
        ],
        "client": ("127.0.0.1", 123),
        "server": ("test", 80),
    }
    sent = False

    async def receive():
        nonlocal sent
        if not sent:
            sent = True
            return {"type": "http.request", "body": body, "more_body": False}
        await asyncio.Event().wait()
        return {"type": "http.disconnect"}

    async def send(message):
        return None

    task = asyncio.create_task(app(scope, receive, send))
    for _ in range(50):
        if consumed:
            break
        await asyncio.sleep(0.02)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert consumed
    assert len(consumed) < 8
    assert app.state.ctx.metrics.cancelled.get("stream", 0) >= 1
