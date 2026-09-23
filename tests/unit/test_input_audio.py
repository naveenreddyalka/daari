"""OpenAI input_audio content blocks must reach frontier (issue #981).

Chat clients that send multimodal turns with inline audio used to lose the
block in content extraction. These tests pin parse + L6 passthrough, and the
optional local ASR inject path when asr.base_url is set.
"""

from __future__ import annotations

import base64

import httpx
import pytest
from httpx import ASGITransport, AsyncClient

from daari.gateway.content import content_to_text, extract_audio
from daari.gateway.internal import ContentAudio, InternalRequest, Message
from daari.router.frontier import FrontierExecutor
from daari.router.router import AppContext
from daari.server.app import create_app
from tests.conftest import META_HEADERS, MOCK_MODEL_CONTENT

# Minimal WAV header + silence; ASR mocks never decode it.
TINY_WAV = base64.b64encode(b"RIFF" + b"\x00" * 36 + b"data" + b"\x00" * 8).decode()


def _audio_blocks(text: str = "what did I say?"):
    return [
        {"type": "text", "text": text},
        {
            "type": "input_audio",
            "input_audio": {"data": TINY_WAV, "format": "wav"},
        },
    ]


class TestExtractAudio:
    def test_openai_input_audio_is_kept(self):
        audio = extract_audio(_audio_blocks())
        assert len(audio) == 1
        assert audio[0].data == TINY_WAV
        assert audio[0].format == "wav"

    def test_text_only_content_has_no_audio(self):
        assert extract_audio("just text") == []
        assert extract_audio([{"type": "text", "text": "hi"}]) == []

    def test_content_to_text_still_returns_the_caption(self):
        assert content_to_text(_audio_blocks("caption")) == "caption"

    def test_missing_data_is_ignored(self):
        assert extract_audio([{"type": "input_audio", "input_audio": {"format": "wav"}}]) == []


class TestFrontierPayload:
    def test_audio_becomes_openai_input_audio_parts(self):
        req = InternalRequest(
            messages=[
                Message(
                    role="user",
                    content="what did I say?",
                    audio=[ContentAudio(data=TINY_WAV, format="wav")],
                )
            ],
            model="gpt-4o",
        )
        messages = FrontierExecutor(
            base_url="http://t", default_model="gpt-4o", api_key="sk"
        )._build_messages(req)
        content = messages[0]["content"]
        assert isinstance(content, list)
        types = [part["type"] for part in content]
        assert "text" in types
        assert "input_audio" in types
        part = next(p for p in content if p["type"] == "input_audio")
        assert part["input_audio"]["data"] == TINY_WAV
        assert part["input_audio"]["format"] == "wav"


def _patch_transport(monkeypatch, transport):
    from daari.gateway import transcriptions

    transcriptions._http = None
    real = httpx.AsyncClient

    class Patched(real):
        def __init__(self, *args, **kwargs):
            if kwargs.get("transport") is None:
                kwargs["transport"] = transport
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", Patched)
    monkeypatch.setattr("daari.gateway.transcriptions.httpx.AsyncClient", Patched)


class TestGatewayPassthrough:
    @pytest.mark.asyncio
    async def test_input_audio_reaches_frontier_payload(self, settings, monkeypatch):
        from daari.gateway.internal import DaariMeta, InternalResponse

        settings.cache.l0.enabled = False
        settings.cache.l1.enabled = False
        settings.frontier.enabled = True
        settings.frontier.base_url = "http://frontier.test/v1"
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        settings.models.capabilities = {
            settings.models.l3: ["tools"],
            settings.models.l4: ["tools"],
            settings.models.l5: ["tools"],
        }

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"message": {"content": "no"}})

        _patch_transport(monkeypatch, httpx.MockTransport(handler))
        app = create_app(settings)
        app.state.ctx = AppContext.from_settings(settings)

        captured: dict = {}

        async def fake_l6(request, *, escalated_from: str, local_confidence: float):
            captured["request"] = request.model_copy(deep=True)
            captured["payload"] = FrontierExecutor(
                base_url="http://t", default_model="gpt-4o", api_key="sk"
            )._build_messages(request)
            return InternalResponse(
                content="Frontier heard the audio turn.",
                model="gpt-4o-mini",
                daari_meta=DaariMeta(
                    tier="L6",
                    executor="frontier",
                    provider_id="openai",
                    latency_ms=10,
                    escalated_from=escalated_from,
                    confidence=local_confidence,
                ),
            )

        monkeypatch.setattr(app.state.ctx.router.frontier, "execute", fake_l6)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/v1/chat/completions",
                json={
                    "model": "daari",
                    "messages": [{"role": "user", "content": _audio_blocks()}],
                },
                headers=META_HEADERS,
            )
        assert response.status_code == 200, response.text
        assert response.json()["daari_meta"]["tier"] == "L6"
        assert "request" in captured
        assert captured["request"].messages[0].audio
        assert captured["request"].messages[0].audio[0].data == TINY_WAV
        content = captured["payload"][0]["content"]
        assert isinstance(content, list)
        audio_parts = [p for p in content if p.get("type") == "input_audio"]
        assert len(audio_parts) == 1
        assert audio_parts[0]["input_audio"]["data"] == TINY_WAV
        assert audio_parts[0]["input_audio"]["format"] == "wav"

    @pytest.mark.asyncio
    async def test_asr_injects_transcript_into_local_prompt(self, settings, monkeypatch):
        settings.cache.l0.enabled = False
        settings.cache.l1.enabled = False
        settings.routing.max_tier_for_chat = "L3"
        settings.asr.base_url = "http://asr.local/v1"
        settings.asr.model = "whisper"
        settings.models.capabilities = {
            settings.models.l3: ["tools"],
            settings.models.l4: ["tools"],
            settings.models.l5: ["tools"],
        }

        ollama_bodies: list[dict] = []

        def handler(request: httpx.Request) -> httpx.Response:
            import json as _json

            if request.url.path.endswith("/audio/transcriptions"):
                return httpx.Response(200, json={"text": "hello from audio"})
            ollama_bodies.append(_json.loads(request.content))
            return httpx.Response(200, json={"message": {"content": MOCK_MODEL_CONTENT}})

        _patch_transport(monkeypatch, httpx.MockTransport(handler))
        app = create_app(settings)
        app.state.ctx = AppContext.from_settings(settings)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/v1/chat/completions",
                json={
                    "model": "daari",
                    "messages": [{"role": "user", "content": _audio_blocks()}],
                },
                headers=META_HEADERS,
            )
        assert response.status_code == 200, response.text
        assert ollama_bodies, "local tier must be called"
        prompt = ollama_bodies[0]["messages"][0]["content"]
        assert "hello from audio" in prompt
