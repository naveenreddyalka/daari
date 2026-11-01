"""lfm3-omni recipe + audio capability routing (#2037)."""

from __future__ import annotations

import base64

import httpx
import pytest
import yaml
from httpx import ASGITransport, AsyncClient

from daari.config.settings import Settings
from daari.gateway.internal import ContentAudio, InternalRequest, Message
from daari.router.capabilities import (
    catalog_from_settings,
    known_model_capabilities,
    required_capabilities,
)
from daari.router.router import AppContext
from daari.server.app import create_app
from daari.setup.doctor import _check_lfm3_omni_unused
from daari.setup.models import (
    LFM3_OMNI_MODEL,
    LFM3_OMNI_RECIPE_NOTE,
    apply_lfm3_omni_speech_recipe,
)
from tests.conftest import META_HEADERS, MOCK_MODEL_CONTENT

TINY_WAV = base64.b64encode(b"RIFF" + b"\x00" * 36 + b"data" + b"\x00" * 8).decode()


def _audio_blocks(text: str = "what did I say?"):
    return [
        {"type": "text", "text": text},
        {
            "type": "input_audio",
            "input_audio": {"data": TINY_WAV, "format": "wav"},
        },
    ]


def test_required_capabilities_detects_audio():
    req = InternalRequest(
        messages=[
            Message(
                role="user",
                content="listen",
                audio=[ContentAudio(data=TINY_WAV, format="wav")],
            )
        ],
        model="daari",
    )
    assert "audio" in required_capabilities(req)


def test_text_only_does_not_require_audio():
    req = InternalRequest(
        messages=[Message(role="user", content="no clips")],
        model="daari",
    )
    assert "audio" not in required_capabilities(req)


def test_lfm3_omni_declares_vision_and_audio():
    caps = known_model_capabilities(LFM3_OMNI_MODEL)
    assert "vision" in caps
    assert "audio" in caps


def test_catalog_picks_up_lfm3_omni_when_wired_as_l4():
    catalog = catalog_from_settings(Settings.model_validate({"models": {"l4": LFM3_OMNI_MODEL}}))
    caps = catalog.for_model(LFM3_OMNI_MODEL)
    assert "audio" in caps
    assert "vision" in caps


def test_lfm3_omni_recipe_dry_run_does_not_write(tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "ollama:\n  base_url: http://127.0.0.1:11434\n"
        "models:\n  l3: llama3.2:3b\n  l4: llama3.1:8b\n",
        encoding="utf-8",
    )
    before = config_path.read_text(encoding="utf-8")
    plan = apply_lfm3_omni_speech_recipe(config_path=config_path, dry_run=True)
    assert plan.changed is True
    assert plan.model == LFM3_OMNI_MODEL
    assert config_path.read_text(encoding="utf-8") == before


def test_lfm3_omni_recipe_wires_speech(tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "ollama:\n  base_url: http://ollama.test:11434\nmodels:\n  l3: llama3.2:3b\n",
        encoding="utf-8",
    )
    result = apply_lfm3_omni_speech_recipe(config_path=config_path, dry_run=False)
    assert result.changed is True
    loaded = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert loaded["tts"]["base_url"] == "http://ollama.test:11434/v1"
    assert loaded["tts"]["model"] == LFM3_OMNI_MODEL
    assert loaded["asr"]["base_url"] == "http://ollama.test:11434/v1"
    assert loaded["asr"]["model"] == LFM3_OMNI_MODEL


def test_lfm3_omni_recipe_note_primary_speech_optional_l4():
    assert "speech" in LFM3_OMNI_RECIPE_NOTE.lower() or "tts" in LFM3_OMNI_RECIPE_NOTE.lower()
    assert "optional" in LFM3_OMNI_RECIPE_NOTE.lower()
    assert "l4" in LFM3_OMNI_RECIPE_NOTE.lower() or "chat" in LFM3_OMNI_RECIPE_NOTE.lower()
    assert f"ollama pull {LFM3_OMNI_MODEL}" in LFM3_OMNI_RECIPE_NOTE
    assert "0.40.13" in LFM3_OMNI_RECIPE_NOTE


def _tags_client(names: list[str]) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/api/tags"):
            return httpx.Response(200, json={"models": [{"name": n} for n in names]})
        return httpx.Response(404)

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_lfm3_omni_tip_when_host_has_tag_but_speech_empty():
    settings = Settings.model_validate(
        {
            "models": {"l4": "llama3.1:8b"},
            "ollama": {"base_url": "http://ollama.test"},
            "tts": {"base_url": ""},
            "asr": {"base_url": ""},
        }
    )
    tip = _check_lfm3_omni_unused(settings, _tags_client([LFM3_OMNI_MODEL, "llama3.1:8b"]))
    assert tip is not None
    assert tip.ok is False
    assert tip.optional is True
    assert tip.name == "ollama_lfm3_omni_unused"
    assert LFM3_OMNI_MODEL in tip.detail
    assert "daari setup models --lfm3-omni" in tip.detail


def test_lfm3_omni_tip_quiet_when_speech_wired():
    settings = Settings.model_validate(
        {
            "models": {"l4": "llama3.1:8b"},
            "ollama": {"base_url": "http://ollama.test"},
            "tts": {"base_url": "http://ollama.test/v1", "model": LFM3_OMNI_MODEL},
            "asr": {"base_url": "http://ollama.test/v1", "model": LFM3_OMNI_MODEL},
        }
    )
    assert _check_lfm3_omni_unused(settings, _tags_client([LFM3_OMNI_MODEL])) is None


def test_lfm3_omni_tip_quiet_when_tag_absent():
    settings = Settings.model_validate(
        {
            "models": {"l4": "llama3.1:8b"},
            "ollama": {"base_url": "http://ollama.test"},
        }
    )
    assert _check_lfm3_omni_unused(settings, _tags_client(["llama3.1:8b"])) is None


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


@pytest.mark.asyncio
async def test_audio_on_text_only_stack_returns_422(settings, monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"message": {"content": MOCK_MODEL_CONTENT}})

    _patch_transport(monkeypatch, httpx.MockTransport(handler))
    settings.cache.l0.enabled = False
    settings.cache.l1.enabled = False
    settings.frontier.enabled = False
    settings.routing.max_tier_for_chat = "L3"
    settings.models.capabilities = {
        settings.models.l3: ["tools"],
        settings.models.l4: ["tools"],
        settings.models.l5: ["tools"],
    }
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
    assert response.status_code == 422, response.text
    assert "audio" in response.text.lower()


@pytest.mark.asyncio
async def test_audio_escalates_to_lfm3_omni_l4(settings, monkeypatch):
    bodies: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        import json as _json

        bodies.append(_json.loads(request.content))
        return httpx.Response(200, json={"message": {"content": MOCK_MODEL_CONTENT}})

    _patch_transport(monkeypatch, httpx.MockTransport(handler))
    settings.cache.l0.enabled = False
    settings.cache.l1.enabled = False
    settings.frontier.enabled = False
    settings.models.l3 = "llama3.2:3b"
    settings.models.l4 = LFM3_OMNI_MODEL
    settings.models.capabilities = {
        "llama3.2:3b": ["tools"],
        LFM3_OMNI_MODEL: ["tools", "vision", "audio"],
        settings.models.l5: ["tools"],
    }
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
    assert response.json()["daari_meta"]["tier"] == "L4"
    assert bodies, "omni L4 must be called"


def test_filter_refuses_when_no_audio_candidate():
    from daari.router.capabilities import CapabilityCatalog, filter_tiers_by_capability

    catalog = CapabilityCatalog(
        models={
            "tiny": frozenset({"tools"}),
            "mid": frozenset({"tools", "vision"}),
        }
    )
    kept = filter_tiers_by_capability(
        ["L3", "L4", "L5"],
        tier_models={"L3": "tiny", "L4": "mid", "L5": "tiny"},
        catalog=catalog,
        required={"audio"},
    )
    assert kept == []
