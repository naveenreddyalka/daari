"""Local-first POST /v1/audio/speech (#847)."""

from __future__ import annotations

import httpx
import pytest
from httpx import ASGITransport, AsyncClient

from daari.auth.virtual_keys import VirtualKeyStore
from daari.gateway.speech import resolve_tts_target
from daari.router.router import AppContext
from daari.server.app import create_app

AUDIO = b"ID3fake-mp3-bytes"


def _patch_upstream(monkeypatch, handler):
    from daari.gateway import speech

    speech._http = None
    real = httpx.AsyncClient

    class Patched(real):
        def __init__(self, *args, **kwargs):
            if kwargs.get("transport") is None:
                kwargs["transport"] = httpx.MockTransport(handler)
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", Patched)
    monkeypatch.setattr("daari.gateway.speech.httpx.AsyncClient", Patched)


def _ok_handler(seen: list[httpx.Request]):
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, content=AUDIO, headers={"content-type": "audio/mpeg"})

    return handler


def _app(settings):
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    return app


def _spend_rows(app):
    ledger = app.state.ctx.router.spend_ledger
    return list(ledger.iter_rows(since="2000-01-01T00:00:00+00:00"))


def _enable_spend(settings, tmp_path):
    settings.usage.spend.enabled = True
    settings.usage.spend.path = str(tmp_path / "spend.sqlite3")


def test_default_tts_settings_are_unset(settings):
    assert settings.tts.base_url == ""
    assert settings.tts.model == ""
    assert settings.tts.voice == ""
    assert resolve_tts_target(settings) is None


def test_openapi_lists_speech(settings):
    schema = create_app(settings).openapi()
    assert "/v1/audio/speech" in schema["paths"]
    assert "post" in schema["paths"]["/v1/audio/speech"]


@pytest.mark.asyncio
async def test_unconfigured_tts_returns_501(settings):
    app = _app(settings)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/audio/speech",
            json={"model": "tts-1", "input": "hello", "voice": "alloy"},
        )
    assert response.status_code == 501
    error = response.json()["error"]
    assert error["type"] == "tts_unavailable"
    assert "tts.base_url" in error["message"]


@pytest.mark.asyncio
async def test_local_tts_proxies_json_and_returns_audio(settings, monkeypatch):
    seen: list[httpx.Request] = []
    _patch_upstream(monkeypatch, _ok_handler(seen))
    settings.tts.base_url = "http://tts.local/v1/"
    app = _app(settings)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/audio/speech",
            json={
                "model": "tts-1",
                "input": "Hello from daari",
                "voice": "alloy",
                "response_format": "mp3",
            },
        )
    assert response.status_code == 200, response.text
    assert response.content == AUDIO
    assert response.headers["content-type"].startswith("audio/mpeg")
    assert len(seen) == 1
    assert seen[0].url.path.endswith("/audio/speech")
    body = seen[0].read()
    import json

    payload = json.loads(body)
    assert payload["model"] == "tts-1"
    assert payload["input"] == "Hello from daari"
    assert payload["voice"] == "alloy"
    assert payload["response_format"] == "mp3"


@pytest.mark.asyncio
async def test_tts_settings_model_overrides_client(settings, monkeypatch):
    seen: list[httpx.Request] = []
    _patch_upstream(monkeypatch, _ok_handler(seen))
    settings.tts.base_url = "http://tts.local/v1"
    settings.tts.model = "kokoro"
    settings.tts.voice = "af_bella"
    app = _app(settings)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/audio/speech",
            json={"model": "tts-1", "input": "hi"},
        )
    assert response.status_code == 200
    import json

    payload = json.loads(seen[0].read())
    assert payload["model"] == "kokoro"
    assert payload["voice"] == "af_bella"


@pytest.mark.asyncio
async def test_tts_empty_input_is_400(settings, monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("must not call upstream")

    _patch_upstream(monkeypatch, handler)
    settings.tts.base_url = "http://tts.local/v1"
    app = _app(settings)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/audio/speech",
            json={"model": "tts-1", "input": "  "},
        )
    assert response.status_code == 400
    assert response.json()["error"]["type"] == "invalid_request_error"


@pytest.mark.asyncio
async def test_tts_spend_row_uses_tts_tier(settings, tmp_path, monkeypatch):
    seen: list[httpx.Request] = []
    _patch_upstream(monkeypatch, _ok_handler(seen))
    _enable_spend(settings, tmp_path)
    settings.server.api_key = "master"
    settings.server.virtual_keys.path = str(tmp_path / "vk.sqlite3")
    settings.tts.base_url = "http://tts.local/v1"
    settings.tts.model = "kokoro"
    store = VirtualKeyStore(settings.virtual_keys_path)
    key = store.create("bot", client_id="client-bot", team="eng")
    app = _app(settings)
    app.state.virtual_key_store = store
    app.state.ctx.virtual_key_store = store

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/audio/speech",
            json={"model": "ignored", "input": "charge me"},
            headers={"Authorization": f"Bearer {key.plaintext}"},
        )
    assert response.status_code == 200, response.text
    rows = _spend_rows(app)
    assert len(rows) == 1
    assert rows[0]["tier"] == "tts"
    assert rows[0]["key_id"] == key.key.key_id
    assert rows[0]["team_id"] == key.key.team_id
    assert rows[0]["model"] == "kokoro"
    assert app.state.ctx.metrics.snapshot(include_histograms=True)["tiers"]["tts"]["count"] == 1
    from daari.gateway.cost_headers import COST_HEADER, TIER_HEADER

    assert response.headers[TIER_HEADER] == "tts"
    assert float(response.headers[COST_HEADER]) == float(rows[0]["cost_usd"]) == 0.0


@pytest.mark.asyncio
async def test_tts_model_allowlist_blocks(settings, tmp_path, monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("must not call upstream")

    _patch_upstream(monkeypatch, handler)
    settings.server.api_key = "master"
    settings.server.virtual_keys.path = str(tmp_path / "vk.sqlite3")
    settings.tts.base_url = "http://tts.local/v1"
    store = VirtualKeyStore(settings.virtual_keys_path)
    locked = store.create("locked", allowed_models=["kokoro"])
    app = _app(settings)
    app.state.virtual_key_store = store
    app.state.ctx.virtual_key_store = store

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/audio/speech",
            json={"model": "tts-1", "input": "nope"},
            headers={"Authorization": f"Bearer {locked.plaintext}"},
        )
    assert response.status_code == 403
    assert response.json()["error"]["type"] == "model_not_allowed"
