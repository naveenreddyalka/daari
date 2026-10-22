"""Gzip buffered JSON responses larger than 16 KiB off the event loop (#1710)."""

from __future__ import annotations

import gzip
import json
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.responses import StreamingResponse

from daari.observability.metrics import Metrics
from daari.observability.prometheus import render_prometheus
from daari.server.app import create_app
from daari.server.gzip_json import GZIP_MIN_BYTES, GzipJsonMiddleware, install_gzip_json


def _app(*, metrics: Metrics | None = None) -> FastAPI:
    app = FastAPI()

    @app.get("/small")
    async def small():
        return {"ok": True}

    @app.get("/big")
    async def big():
        return {"blob": "x" * (GZIP_MIN_BYTES + 64)}

    @app.get("/stream")
    async def stream():
        async def chunks():
            yield b"data: " + b"z" * (GZIP_MIN_BYTES + 32) + b"\n\n"

        return StreamingResponse(chunks(), media_type="text/event-stream")

    if metrics is not None:
        app.state.ctx = SimpleNamespace(metrics=metrics)
    install_gzip_json(app)
    return app


async def _raw(app: FastAPI, path: str, accept: str | None):
    messages: list[dict] = []
    headers = []
    if accept is not None:
        headers.append((b"accept-encoding", accept.encode()))
    scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.4"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "headers": headers,
        "client": ("127.0.0.1", 123),
        "server": ("test", 80),
    }

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        messages.append(message)

    await app(scope, receive, send)
    start = next(m for m in messages if m["type"] == "http.response.start")
    body = b"".join(m.get("body", b"") for m in messages if m["type"] == "http.response.body")
    decoded_headers = {
        k.decode().lower(): v.decode() for k, v in start["headers"]
    }
    return start["status"], decoded_headers, body


@pytest.mark.asyncio
async def test_large_json_is_gzipped_off_the_event_loop(monkeypatch):
    calls: list[object] = []

    async def fake_to_thread(fn, /, *args, **kwargs):
        calls.append(fn)
        return fn(*args, **kwargs)

    monkeypatch.setattr("daari.server.gzip_json.asyncio.to_thread", fake_to_thread)
    status, headers, body = await _raw(_app(), "/big", "gzip")
    assert status == 200
    assert headers["content-encoding"] == "gzip"
    assert "accept-encoding" in headers["vary"].lower()
    assert json.loads(gzip.decompress(body))["blob"].startswith("x")
    assert calls, "compression must run via asyncio.to_thread"


@pytest.mark.asyncio
async def test_small_json_and_missing_accept_encoding_stay_plain(monkeypatch):
    calls: list[object] = []

    async def fake_to_thread(fn, /, *args, **kwargs):
        calls.append(fn)
        return fn(*args, **kwargs)

    monkeypatch.setattr("daari.server.gzip_json.asyncio.to_thread", fake_to_thread)
    app = _app()
    status, headers, body = await _raw(app, "/small", "gzip")
    assert status == 200
    assert "content-encoding" not in headers
    assert json.loads(body)["ok"] is True

    status, headers, body = await _raw(app, "/big", None)
    assert status == 200
    assert "content-encoding" not in headers
    assert json.loads(body)["blob"].startswith("x")
    assert calls == []


@pytest.mark.asyncio
async def test_body_at_threshold_is_not_compressed():
    app = FastAPI()

    @app.get("/exact")
    async def exact():
        from starlette.responses import Response

        return Response(content=b"{" + b"a" * (GZIP_MIN_BYTES - 2) + b"}", media_type="application/json")

    install_gzip_json(app)
    status, headers, body = await _raw(app, "/exact", "gzip, deflate")
    assert status == 200
    assert len(body) == GZIP_MIN_BYTES
    assert "content-encoding" not in headers


@pytest.mark.asyncio
async def test_sse_is_not_compressed():
    status, headers, body = await _raw(_app(), "/stream", "gzip")
    assert status == 200
    assert "content-encoding" not in headers
    assert body.startswith(b"data: ")
    assert b"text/event-stream" in headers["content-type"].encode() or "event-stream" in headers["content-type"]


def test_create_app_registers_gzip_middleware(settings):
    app = create_app(settings)
    assert any(getattr(m, "cls", None) is GzipJsonMiddleware for m in app.user_middleware)


@pytest.mark.asyncio
async def test_gzip_metrics_compressed_and_below_min(monkeypatch):
    """Large JSON bumps compressed counters; small JSON skips with below_min (#1830)."""
    async def fake_to_thread(fn, /, *args, **kwargs):
        return fn(*args, **kwargs)

    monkeypatch.setattr("daari.server.gzip_json.asyncio.to_thread", fake_to_thread)
    metrics = Metrics()
    app = _app(metrics=metrics)

    status, headers, body = await _raw(app, "/big", "gzip")
    assert status == 200
    assert headers["content-encoding"] == "gzip"
    snap = metrics.snapshot(include_histograms=True)
    assert snap["gzip"].get("compressed") == 1
    assert snap["gzip_bytes_before"] > GZIP_MIN_BYTES
    assert 0 < snap["gzip_bytes_after"] < snap["gzip_bytes_before"]
    text = render_prometheus(metrics)
    assert 'daari_gzip_total{result="compressed"} 1' in text
    assert f"daari_gzip_uncompressed_bytes_total {snap['gzip_bytes_before']}" in text
    assert f"daari_gzip_compressed_bytes_total {snap['gzip_bytes_after']}" in text

    status, headers, body = await _raw(app, "/small", "gzip")
    assert status == 200
    assert "content-encoding" not in headers
    snap = metrics.snapshot(include_histograms=True)
    assert snap["gzip"].get("skipped:below_min") == 1
    text = render_prometheus(metrics)
    assert 'daari_gzip_total{result="skipped",reason="below_min"} 1' in text


def test_gzip_prometheus_zero_on_empty_metrics():
    text = render_prometheus(Metrics())
    assert "daari_gzip_total 0" in text
    assert "daari_gzip_uncompressed_bytes_total 0" in text
    assert "daari_gzip_compressed_bytes_total 0" in text
