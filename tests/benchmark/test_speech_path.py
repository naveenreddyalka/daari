"""Hermetic micro-benchmarks for TTS speech finalize + voices catalog (#1938).

No Ollama. Marked ``@pytest.mark.benchmark`` so default CI skips them.
Ceilings are deliberately loose (~10× headroom over typical local means) so
only order-of-magnitude regressions fail.
"""

from __future__ import annotations

import time
from contextlib import asynccontextmanager

import httpx
import pytest
from httpx import ASGITransport, AsyncClient

from daari.auth.virtual_keys import VirtualKeyStore
from daari.gateway import speech
from daari.router.router import AppContext
from daari.server.app import create_app

# Loose absolute ceilings (seconds). Documented so a 10× regression trips CI
# when someone opts into ``pytest -m benchmark``.
SPEECH_STREAM_FINALIZE_CEILING_S = 0.500  # stream drain + spend/ledger finalize
VOICES_CATALOG_CEILING_S = 0.200  # GET /v1/audio/voices Phonon fallback build
SPEECH_STREAM_FINALIZE_CYCLES = 20
VOICES_CATALOG_CYCLES = 40


def _median(samples: list[float]) -> float:
    ordered = sorted(samples)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2.0


def _app(settings):
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    return app


def _enable_spend(settings, tmp_path) -> None:
    settings.usage.spend.enabled = True
    settings.usage.spend.path = str(tmp_path / "spend.sqlite3")


def _spend_rows(app) -> list:
    ledger = app.state.ctx.router.spend_ledger
    return list(ledger.iter_rows(since="2000-01-01T00:00:00+00:00"))


@pytest.mark.benchmark
@pytest.mark.asyncio
async def test_speech_stream_finalize_under_ceiling(settings, tmp_path, monkeypatch):
    """Streamed speech drain + _finalize_speech spend/ledger — mocked upstream (#1938).

    Ceiling: SPEECH_STREAM_FINALIZE_CEILING_S (0.500s) median over
    SPEECH_STREAM_FINALIZE_CYCLES cycles. Guards regressions in stream
    collect → finalize → spend row write without live TTS.
    """
    from fastapi.responses import StreamingResponse

    class _FakeUpstream:
        status_code = 200
        headers = httpx.Headers(
            {"content-type": "audio/mpeg", "transfer-encoding": "chunked"}
        )

        async def aiter_bytes(self, chunk_size: int = 65536):
            yield b"AA"
            yield b"BB"

        async def aread(self):
            raise AssertionError("stream path must not buffer via aread")

    @asynccontextmanager
    async def _fake_stream(client, method, url, **kwargs):
        yield _FakeUpstream()

    monkeypatch.setattr(speech, "deadline_bounded_stream", _fake_stream)
    speech._http = httpx.AsyncClient()
    _enable_spend(settings, tmp_path)
    settings.server.api_key = "master"
    settings.server.virtual_keys.path = str(tmp_path / "vk.sqlite3")
    settings.tts.base_url = "http://tts.local/v1"
    settings.tts.model = "kokoro"
    store = VirtualKeyStore(settings.virtual_keys_path)
    key = store.create("bench-tts", client_id="client-tts-bench", team="eng")
    app = _app(settings)
    app.state.virtual_key_store = store
    app.state.ctx.virtual_key_store = store

    from starlette.requests import Request

    def _make_request() -> Request:
        scope = {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "POST",
            "scheme": "http",
            "path": "/v1/audio/speech",
            "raw_path": b"/v1/audio/speech",
            "query_string": b"",
            "headers": [
                (b"host", b"test"),
                (b"authorization", f"Bearer {key.plaintext}".encode()),
            ],
            "client": ("127.0.0.1", 123),
            "server": ("test", 80),
            "app": app,
        }

        async def _receive():
            return {"type": "http.request", "body": b"", "more_body": False}

        request = Request(scope, _receive)
        request.state.auth_claims = type(
            "Claims",
            (),
            {
                "key_id": key.key.key_id,
                "client_id": key.key.client_id,
                "team_id": key.key.team_id,
                "virtual_key": key.key,
            },
        )()
        return request

    # Warm path once outside the timed loop.
    warm = await speech.handle_speech(
        _make_request(),
        model="tts-1",
        input_text="warm",
        voice="alloy",
        response_format="mp3",
    )
    assert isinstance(warm, StreamingResponse)
    async for _ in warm.body_iterator:
        pass
    assert _spend_rows(app)

    samples: list[float] = []
    for i in range(SPEECH_STREAM_FINALIZE_CYCLES):
        start = time.perf_counter()
        response = await speech.handle_speech(
            _make_request(),
            model="tts-1",
            input_text=f"bench-{i}",
            voice="alloy",
            response_format="mp3",
        )
        assert isinstance(response, StreamingResponse)
        collected = b""
        async for chunk in response.body_iterator:
            collected += chunk
        samples.append(time.perf_counter() - start)
        assert collected == b"AABB"

    await speech.aclose_http()

    median = _median(samples)
    assert median < SPEECH_STREAM_FINALIZE_CEILING_S, (
        f"speech stream finalize median {median:.4f}s exceeds ceiling "
        f"{SPEECH_STREAM_FINALIZE_CEILING_S}s (10×-regression guard)"
    )
    assert len(_spend_rows(app)) >= 1 + SPEECH_STREAM_FINALIZE_CYCLES


@pytest.mark.benchmark
@pytest.mark.asyncio
async def test_voices_phonon_fallback_catalog_under_ceiling(
    settings, tmp_path, monkeypatch
):
    """GET /v1/audio/voices Phonon fallback catalog build — no network (#1938).

    Ceiling: VOICES_CATALOG_CEILING_S (0.200s) median over VOICES_CATALOG_CYCLES
    cycles. Guards regressions in fallback voice list + OpenAI alias merge.
    """

    async def _fallback(target, model_name="", client=None):
        return speech.phonon_fallback_voices()

    monkeypatch.setattr(speech, "fetch_phonon_voice_names", _fallback)
    settings.tts.base_url = "http://127.0.0.1:11434/v1"
    settings.tts.model = "phonon"
    app = _app(settings)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Warm ASGI + catalog once.
        warm = await client.get("/v1/audio/voices")
        assert warm.status_code == 200
        assert warm.json()["object"] == "list"

        samples: list[float] = []
        for _ in range(VOICES_CATALOG_CYCLES):
            start = time.perf_counter()
            response = await client.get("/v1/audio/voices")
            samples.append(time.perf_counter() - start)
            assert response.status_code == 200
            body = response.json()
            ids = {row["id"] for row in body["data"]}
            assert "Zoey" in ids
            assert "alloy" in ids

    median = _median(samples)
    assert median < VOICES_CATALOG_CEILING_S, (
        f"voices catalog median {median:.4f}s exceeds ceiling "
        f"{VOICES_CATALOG_CEILING_S}s (10×-regression guard)"
    )
