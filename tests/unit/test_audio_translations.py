"""Local-first POST /v1/audio/translations (#758)."""

from __future__ import annotations

import httpx
import pytest
from httpx import ASGITransport, AsyncClient

from daari.router.router import AppContext
from daari.server.app import create_app

AUDIO = b"RIFF"


def _patch_upstream(monkeypatch, handler):
    real = httpx.AsyncClient

    class Patched(real):
        def __init__(self, *args, **kwargs):
            if kwargs.get("transport") is None:
                kwargs["transport"] = httpx.MockTransport(handler)
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", Patched)


def _app(settings):
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    return app


async def _post(client: AsyncClient, *, data: dict | None = None):
    body = {"model": "whisper-1", "response_format": "json"}
    if data is not None:
        body = data
    return await client.post(
        "/v1/audio/translations",
        files={"file": ("note.wav", AUDIO, "audio/wav")},
        data=body,
    )


@pytest.mark.asyncio
async def test_local_asr_forwards_translation(settings, monkeypatch):
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"text": "hello in english"})

    _patch_upstream(monkeypatch, handler)
    settings.asr.base_url = "http://asr.local/v1/"
    app = _app(settings)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await _post(client, data={"model": "whisper-1", "response_format": "json", "prompt": "meeting"})

    assert response.status_code == 200
    assert response.json()["text"] == "hello in english"
    assert len(seen) == 1
    request = seen[0]
    assert str(request.url) == "http://asr.local/v1/audio/translations"
    assert b"RIFF" in request.content
    assert b"whisper-1" in request.content
    assert "authorization" not in request.headers


@pytest.mark.asyncio
async def test_unconfigured_translation_returns_501(settings, monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("must not upload audio")

    _patch_upstream(monkeypatch, handler)
    app = _app(settings)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await _post(client)

    assert response.status_code == 501
    error = response.json()["error"]
    assert error["type"] == "asr_unavailable"
    assert "asr.base_url" in error["message"]


@pytest.mark.asyncio
async def test_non_json_translation_format_is_400(settings, monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("must not upload unsupported formats")

    _patch_upstream(monkeypatch, handler)
    settings.asr.base_url = "http://asr.local/v1"
    app = _app(settings)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await _post(client, data={"model": "whisper-1", "response_format": "srt"})

    assert response.status_code == 400
    assert "json" in response.json()["error"]["message"]
