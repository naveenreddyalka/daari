"""Retired-model 410 on modality, MCP, and batch doors (#1701)."""

from __future__ import annotations

import httpx
import pytest
from httpx import ASGITransport, AsyncClient

from daari.auth.rate_limit import MemoryCounterBackend, RateLimiter
from daari.auth.virtual_keys import VirtualKeyStore
from daari.config.settings import FrontierProviderConfig
from daari.enterprise.audit import AuditLog
from daari.gateway.batches import BatchGovernance, BatchItemRejected, BatchStore
from daari.gateway.internal import DaariMeta, InternalRequest, InternalResponse
from daari.gateway.openai import _execute_batch_chat_body
from daari.router.router import AppContext
from daari.server.app import create_app
from tests.conftest import mock_all_ollama_executors

_PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 24


def _settings(settings, tmp_path):
    settings.models.lifecycle = {"retired-model": {"lifecycle": "retired"}}
    settings.models.reject_retired = True
    settings.enterprise.audit_path = str(tmp_path / "audit.sqlite3")
    settings.frontier.enabled = True
    settings.frontier.providers = [
        FrontierProviderConfig(
            id="openai",
            base_url="https://api.openai.com/v1",
            model="dall-e-3",
            keys=["sk-test"],
        )
    ]
    settings.tts.base_url = "http://tts.local/v1"
    settings.asr.base_url = "http://asr.local/v1"
    return settings


def _app(settings):
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    return app


def _patch_module(monkeypatch, module_path: str):
    module = __import__(module_path, fromlist=["_http"])
    module._http = None
    real = httpx.AsyncClient

    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError(f"upstream must not run: {request.url}")

    class Patched(real):
        def __init__(self, *args, **kwargs):
            if kwargs.get("transport") is None:
                kwargs["transport"] = httpx.MockTransport(handler)
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", Patched)
    monkeypatch.setattr(f"{module_path}.httpx.AsyncClient", Patched)


def _assert_retired(response, app, tmp_path) -> None:
    assert response.status_code == 410, response.text
    err = response.json()["error"]
    assert err["type"] == "model_retired"
    assert err["code"] == "model_retired"
    rows = AuditLog(tmp_path / "audit.sqlite3").list(action="models.retired_denied")
    assert rows
    assert rows[-1]["detail"]["model"] == "retired-model"
    rejects = app.state.ctx.metrics.snapshot(include_histograms=True)["rejects"]
    assert rejects.get("retired", 0) >= 1


@pytest.mark.asyncio
async def test_images_generations_rejects_retired_model(settings, monkeypatch, tmp_path):
    _settings(settings, tmp_path)
    _patch_module(monkeypatch, "daari.gateway.images")
    app = _app(settings)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/images/generations",
            json={"model": "retired-model", "prompt": "a cat"},
        )
    _assert_retired(response, app, tmp_path)


@pytest.mark.asyncio
async def test_images_edits_rejects_retired_model(settings, monkeypatch, tmp_path):
    _settings(settings, tmp_path)
    _patch_module(monkeypatch, "daari.gateway.images")
    app = _app(settings)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/images/edits",
            data={"model": "retired-model", "prompt": "make it blue"},
            files={"image": ("src.png", _PNG, "image/png")},
        )
    _assert_retired(response, app, tmp_path)


@pytest.mark.asyncio
async def test_images_variations_rejects_retired_model(settings, monkeypatch, tmp_path):
    _settings(settings, tmp_path)
    _patch_module(monkeypatch, "daari.gateway.images")
    app = _app(settings)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/images/variations",
            data={"model": "retired-model"},
            files={"image": ("src.png", _PNG, "image/png")},
        )
    _assert_retired(response, app, tmp_path)


@pytest.mark.asyncio
async def test_speech_rejects_retired_model(settings, monkeypatch, tmp_path):
    _settings(settings, tmp_path)
    _patch_module(monkeypatch, "daari.gateway.speech")
    app = _app(settings)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/audio/speech",
            json={"model": "retired-model", "input": "hello", "voice": "alloy"},
        )
    _assert_retired(response, app, tmp_path)


@pytest.mark.asyncio
async def test_transcriptions_rejects_retired_model(settings, monkeypatch, tmp_path):
    _settings(settings, tmp_path)
    _patch_module(monkeypatch, "daari.gateway.transcriptions")
    app = _app(settings)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/audio/transcriptions",
            data={"model": "retired-model"},
            files={"file": ("a.wav", b"RIFF", "audio/wav")},
        )
    _assert_retired(response, app, tmp_path)


@pytest.mark.asyncio
async def test_moderations_rejects_retired_model(settings, monkeypatch, tmp_path):
    _settings(settings, tmp_path)
    _patch_module(monkeypatch, "daari.gateway.moderations")
    app = _app(settings)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/moderations",
            json={"model": "retired-model", "input": "hello"},
        )
    _assert_retired(response, app, tmp_path)


@pytest.mark.asyncio
async def test_rerank_rejects_retired_model(settings, monkeypatch, tmp_path):
    _settings(settings, tmp_path)
    _patch_module(monkeypatch, "daari.gateway.rerank")
    app = _app(settings)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/rerank",
            json={
                "model": "retired-model",
                "query": "cats",
                "documents": ["dogs", "cats"],
            },
        )
    _assert_retired(response, app, tmp_path)


@pytest.mark.asyncio
async def test_mcp_provider_tools_call_rejects_retired_model(settings, monkeypatch, tmp_path):
    _settings(settings, tmp_path)
    settings.integrations.mcp_servers = [
        {"id": "weather", "url": "http://mcp.test/weather"},
    ]
    app = _app(settings)
    called = {"n": 0}

    async def fake_execute(request: InternalRequest) -> InternalResponse:
        called["n"] += 1
        return InternalResponse(
            content="sunny",
            model=request.model or "daari",
            daari_meta=DaariMeta(tier="tool", executor="integration", provider_id="mcp:weather"),
        )

    provider = app.state.ctx.providers.get("mcp:weather")
    assert provider is not None
    monkeypatch.setattr(provider, "execute", fake_execute)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/mcp",
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": "mcp_weather",
                    "arguments": {"input": "forecast", "model": "retired-model"},
                },
            },
        )
    _assert_retired(response, app, tmp_path)
    assert called["n"] == 0


@pytest.mark.asyncio
async def test_batch_submission_rejects_retired_item_before_quota(settings, monkeypatch, tmp_path):
    _settings(settings, tmp_path)
    settings.server.virtual_keys.path = str(tmp_path / "vk.sqlite3")
    vk = VirtualKeyStore(settings.virtual_keys_path)
    created = vk.create("agent", client_id="agent", allowed_models=["retired-model"], rpm=1)
    app_ctx = AppContext.from_settings(settings)
    app_ctx.virtual_key_store = vk
    limiter = RateLimiter(MemoryCounterBackend(), max_in_flight=1)
    app_ctx.rate_limiter = limiter
    routed = {"n": 0}

    async def fake(request: InternalRequest) -> InternalResponse:
        routed["n"] += 1
        return InternalResponse(
            content="ok",
            model=request.model or "llama3.2:3b",
            daari_meta=DaariMeta(tier="L3", executor="ollama", provider_id="ollama"),
        )

    mock_all_ollama_executors(monkeypatch, app_ctx.router, fake)
    body = {"model": "retired-model", "messages": [{"role": "user", "content": "hi"}]}
    gov = BatchGovernance(key_id=created.key.key_id, client_id="agent", kind="virtual")
    with pytest.raises(BatchItemRejected) as denied:
        await _execute_batch_chat_body(app_ctx, body, governance=gov, rate_limiter=limiter)
    assert denied.value.error["type"] == "model_retired"
    assert denied.value.error["code"] == "model_retired"
    assert routed["n"] == 0
    assert limiter.in_flight == 0

    store = BatchStore()
    job = store.create(requests=[body], governance=gov)

    async def execute_one(item_body: dict) -> dict:
        return await _execute_batch_chat_body(
            app_ctx, item_body, governance=gov, rate_limiter=limiter
        )

    await store.run_job(job.id, execute_one)
    refreshed = store.get(job.id)
    assert refreshed is not None
    row = refreshed.results[0]
    assert row["response"]["status_code"] == 410
    assert row["error"]["type"] == "model_retired"
    rows = AuditLog(tmp_path / "audit.sqlite3").list(action="models.retired_denied")
    assert rows
    assert limiter.in_flight == 0
