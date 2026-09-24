"""Guardrails on embeddings, speech, ASR, moderations, rerank (#1059)."""

from __future__ import annotations

import httpx
import pytest
from httpx import ASGITransport, AsyncClient

from daari.config.settings import (
    FrontierProviderConfig,
    GuardrailRuleSettings,
    GuardrailSettings,
)
from daari.gateway.guardrails import (
    GuardrailEngine,
    GuardrailRule,
    apply_endpoint_input_policy,
    apply_endpoint_output_policy,
)
from daari.router.router import AppContext
from daari.server.app import create_app


def _enable_block(settings, pattern: str = r"banned"):
    settings.guardrails = GuardrailSettings(
        enabled=True,
        block_message="blocked by policy",
        input_rules=[
            GuardrailRuleSettings(name="nope", pattern=pattern, action="block", kind="deny")
        ],
    )


def _enable_redact(settings, pattern: str = r"SECRET"):
    settings.guardrails = GuardrailSettings(
        enabled=True,
        input_rules=[
            GuardrailRuleSettings(name="scrub", pattern=pattern, action="redact", kind="deny")
        ],
        output_rules=[
            GuardrailRuleSettings(name="scrub_out", pattern=pattern, action="redact", kind="deny")
        ],
    )


def _app(settings):
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    return app


def test_apply_endpoint_input_policy_short_circuits_when_disabled():
    policy = apply_endpoint_input_policy("banned", None)
    assert policy.text == "banned"
    assert policy.blocked is False
    engine = GuardrailEngine(enabled=False)
    assert apply_endpoint_input_policy("banned", engine).blocked is False


def test_apply_endpoint_input_policy_block_and_redact():
    engine = GuardrailEngine(
        enabled=True,
        block_message="nope",
        input_rules=[GuardrailRule(name="nope", pattern=r"banned", action="block")],
    )
    blocked = apply_endpoint_input_policy("this is banned", engine)
    assert blocked.blocked is True
    assert blocked.block_message == "nope"

    redact = GuardrailEngine(
        enabled=True,
        input_rules=[GuardrailRule(name="scrub", pattern=r"SECRET", action="redact")],
    )
    scrubbed = apply_endpoint_input_policy("leak SECRET please", redact)
    assert scrubbed.blocked is False
    assert "SECRET" not in scrubbed.text
    assert "<redacted>" in scrubbed.text


def test_apply_endpoint_output_policy_redacts():
    engine = GuardrailEngine(
        enabled=True,
        output_rules=[GuardrailRule(name="scrub", pattern=r"SECRET", action="redact", kind="deny")],
    )
    out = apply_endpoint_output_policy("heard SECRET words", engine)
    assert "SECRET" not in out.text
    assert "<redacted>" in out.text


@pytest.mark.asyncio
async def test_embeddings_block(settings):
    _enable_block(settings)
    app = _app(settings)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/embeddings",
            json={"model": "daari", "input": "this is banned"},
        )
    assert response.status_code == 400
    body = response.json()
    detail = body.get("detail") or body.get("error") or body
    assert "guardrail_blocked" in str(detail)


@pytest.mark.asyncio
async def test_embeddings_redact_reaches_embedder(settings):
    _enable_redact(settings)
    settings.cache.l1.enabled = True
    app = create_app(settings)
    ctx = AppContext.from_settings(settings)

    class RecordingEmbedder:
        def __init__(self):
            self.calls: list[str] = []

        async def embed(self, text: str, *, model: str | None = None) -> list[float]:
            self.calls.append(text)
            return [0.1, 0.2]

        async def embed_many(
            self, texts: list[str], *, model: str | None = None
        ) -> list[list[float]]:
            return [await self.embed(text, model=model) for text in texts]

    embedder = RecordingEmbedder()
    ctx.router.semantic_cache.embedder = embedder
    app.state.ctx = ctx
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/embeddings",
            json={"model": "daari", "input": "token SECRET here"},
        )
    assert response.status_code == 200, response.text
    assert embedder.calls
    assert all("SECRET" not in text for text in embedder.calls)
    assert any("<redacted>" in text for text in embedder.calls)


def _patch_speech(monkeypatch, handler):
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


@pytest.mark.asyncio
async def test_speech_block(settings, monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("must not call TTS")

    _patch_speech(monkeypatch, handler)
    _enable_block(settings)
    settings.tts.base_url = "http://tts.local/v1"
    settings.tts.model = "kokoro"
    app = _app(settings)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/audio/speech",
            json={"model": "kokoro", "input": "say banned words"},
        )
    assert response.status_code == 400
    assert response.json()["error"]["type"] == "guardrail_blocked"


@pytest.mark.asyncio
async def test_speech_redact(settings, monkeypatch):
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, content=b"ID3audio", headers={"content-type": "audio/mpeg"})

    _patch_speech(monkeypatch, handler)
    _enable_redact(settings)
    settings.tts.base_url = "http://tts.local/v1"
    settings.tts.model = "kokoro"
    app = _app(settings)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/audio/speech",
            json={"model": "kokoro", "input": "speak SECRET aloud"},
        )
    assert response.status_code == 200, response.text
    assert len(seen) == 1
    payload = seen[0].read()
    assert b"SECRET" not in payload
    assert b"<redacted>" in payload


def _patch_moderations(monkeypatch, handler):
    from daari.gateway import moderations

    moderations._http = None
    real = httpx.AsyncClient

    class Patched(real):
        def __init__(self, *args, **kwargs):
            if kwargs.get("transport") is None:
                kwargs["transport"] = httpx.MockTransport(handler)
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", Patched)
    monkeypatch.setattr("daari.gateway.moderations.httpx.AsyncClient", Patched)


def _enable_frontier(settings):
    settings.frontier.enabled = True
    settings.frontier.providers = [
        FrontierProviderConfig(
            id="openai",
            base_url="https://api.openai.com/v1",
            model="gpt-4o",
            keys=["sk-test"],
        )
    ]


@pytest.mark.asyncio
async def test_moderations_block(settings, monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("must not call moderations")

    _patch_moderations(monkeypatch, handler)
    _enable_frontier(settings)
    _enable_block(settings)
    app = _app(settings)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/v1/moderations", json={"input": "banned phrase"})
    assert response.status_code == 400
    assert response.json()["error"]["type"] == "guardrail_blocked"


@pytest.mark.asyncio
async def test_moderations_redact(settings, monkeypatch):
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            200,
            json={"id": "modr", "model": "omni-moderation-latest", "results": [{"flagged": False}]},
        )

    _patch_moderations(monkeypatch, handler)
    _enable_frontier(settings)
    _enable_redact(settings)
    app = _app(settings)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/v1/moderations", json={"input": "has SECRET inside"})
    assert response.status_code == 200, response.text
    payload = seen[0].read()
    assert b"SECRET" not in payload
    assert b"<redacted>" in payload


def _patch_rerank(monkeypatch, handler):
    from daari.gateway import rerank

    rerank._http = None
    real = httpx.AsyncClient

    class Patched(real):
        def __init__(self, *args, **kwargs):
            if kwargs.get("transport") is None:
                kwargs["transport"] = httpx.MockTransport(handler)
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", Patched)
    monkeypatch.setattr("daari.gateway.rerank.httpx.AsyncClient", Patched)


@pytest.mark.asyncio
async def test_rerank_block(settings, monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("must not call rerank")

    _patch_rerank(monkeypatch, handler)
    _enable_frontier(settings)
    _enable_block(settings)
    app = _app(settings)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/rerank",
            json={"query": "banned query", "documents": ["ok doc"]},
        )
    assert response.status_code == 400
    assert response.json()["error"]["type"] == "guardrail_blocked"


@pytest.mark.asyncio
async def test_rerank_redact(settings, monkeypatch):
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"results": [{"index": 0, "relevance_score": 0.5}]})

    _patch_rerank(monkeypatch, handler)
    _enable_frontier(settings)
    _enable_redact(settings)
    app = _app(settings)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/rerank",
            json={"query": "find SECRET", "documents": ["doc with SECRET"]},
        )
    assert response.status_code == 200, response.text
    payload = seen[0].read()
    assert b"SECRET" not in payload
    assert b"<redacted>" in payload


def _patch_asr(monkeypatch, handler):
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
async def test_transcriptions_prompt_block(settings, monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("must not call ASR")

    _patch_asr(monkeypatch, handler)
    _enable_block(settings)
    settings.asr.base_url = "http://asr.local/v1"
    settings.asr.model = "whisper"
    app = _app(settings)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/audio/transcriptions",
            files={"file": ("a.wav", b"RIFF", "audio/wav")},
            data={"model": "whisper", "prompt": "banned hint"},
        )
    assert response.status_code == 400
    assert response.json()["error"]["type"] == "guardrail_blocked"


@pytest.mark.asyncio
async def test_transcriptions_output_redact(settings, monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"text": "transcript has SECRET in it"})

    _patch_asr(monkeypatch, handler)
    _enable_redact(settings)
    settings.asr.base_url = "http://asr.local/v1"
    settings.asr.model = "whisper"
    app = _app(settings)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/audio/transcriptions",
            files={"file": ("a.wav", b"RIFF", "audio/wav")},
            data={"model": "whisper"},
        )
    assert response.status_code == 200, response.text
    text = response.json()["text"]
    assert "SECRET" not in text
    assert "<redacted>" in text


@pytest.mark.asyncio
async def test_transcriptions_frontier_respects_no_frontier(settings, monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("must not upload audio to frontier")

    _patch_asr(monkeypatch, handler)
    settings.asr.base_url = ""
    settings.asr.frontier_fallback = True
    _enable_frontier(settings)
    app = _app(settings)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/audio/transcriptions",
            files={"file": ("a.wav", b"RIFF", "audio/wav")},
            data={"model": "whisper"},
            headers={"X-Daari-No-Frontier": "true"},
        )
    assert response.status_code == 403
    assert response.json()["error"]["type"] == "frontier_not_allowed"
