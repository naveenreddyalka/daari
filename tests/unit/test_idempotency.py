"""Idempotency-Key replay on chat completions and Responses (#714)."""

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
