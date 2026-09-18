"""Local-first POST /v1/audio/transcriptions (#715)."""

from __future__ import annotations

import httpx
import pytest
from httpx import ASGITransport, AsyncClient

from daari.auth.virtual_keys import BudgetWindow, VirtualKeyStore
from daari.config.settings import FrontierProviderConfig
from daari.gateway.transcriptions import resolve_asr_target
from daari.observability.usage import UsageLedger
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


def _ok_handler(seen: list[httpx.Request]):
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"text": "hello from asr"})

    return handler


def _form(model: str = "whisper-1", **extra: str):
    data = {"model": model, "response_format": "json"}
    data.update(extra)
    return data


async def _post(client: AsyncClient, *, headers: dict | None = None, data: dict | None = None):
    return await client.post(
        "/v1/audio/transcriptions",
        files={"file": ("note.wav", AUDIO, "audio/wav")},
        data=data if data is not None else _form(),
        headers=headers,
    )


def _app(settings):
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    return app


def test_default_asr_settings_are_unset(settings):
    assert settings.asr.base_url == ""
    assert settings.asr.model == ""
    assert settings.asr.frontier_fallback is False


def test_openapi_lists_transcriptions(settings):
    schema = create_app(settings).openapi()
    assert "/v1/audio/transcriptions" in schema["paths"]
    assert "post" in schema["paths"]["/v1/audio/transcriptions"]


@pytest.mark.asyncio
async def test_local_asr_forwards_multipart_and_returns_text(settings, monkeypatch):
    seen: list[httpx.Request] = []
    _patch_upstream(monkeypatch, _ok_handler(seen))
    settings.asr.base_url = "http://asr.local/v1/"
    app = _app(settings)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await _post(
            client,
            data=_form(language="en", prompt="meeting"),
        )

    assert response.status_code == 200
    assert response.json()["text"] == "hello from asr"
    assert len(seen) == 1
    request = seen[0]
    assert str(request.url) == "http://asr.local/v1/audio/transcriptions"
    assert b"RIFF" in request.content
    assert b"whisper-1" in request.content
    assert b"language" in request.content
    assert b"meeting" in request.content
    assert "authorization" not in request.headers


@pytest.mark.asyncio
async def test_configured_model_overrides_client_model(settings, monkeypatch):
    seen: list[httpx.Request] = []
    _patch_upstream(monkeypatch, _ok_handler(seen))
    settings.asr.base_url = "http://asr.local/v1"
    settings.asr.model = "ggml-base"
    app = _app(settings)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await _post(client, data=_form("whisper-1"))

    assert response.status_code == 200
    assert b"ggml-base" in seen[0].content
    assert b"whisper-1" not in seen[0].content


@pytest.mark.asyncio
async def test_unconfigured_asr_returns_501(settings, monkeypatch):
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
    assert "frontier_fallback" in error["message"]


@pytest.mark.asyncio
async def test_frontier_without_fallback_never_uploads(settings, monkeypatch):
    monkeypatch.setenv("DAARI_FRONTIER_API_KEY", "sk-should-not-leak")
    settings.frontier.enabled = True
    settings.frontier.base_url = "https://frontier.example/v1"
    settings.asr.frontier_fallback = False

    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError(f"uploaded to {request.url}")

    _patch_upstream(monkeypatch, handler)
    app = _app(settings)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await _post(client)

    assert response.status_code == 501


@pytest.mark.asyncio
async def test_frontier_fallback_posts_to_configured_base(settings, monkeypatch):
    seen: list[httpx.Request] = []
    _patch_upstream(monkeypatch, _ok_handler(seen))
    monkeypatch.setenv("DAARI_FRONTIER_API_KEY", "sk-frontier-test")
    settings.frontier.enabled = True
    settings.frontier.base_url = "https://frontier.example/v1"
    settings.asr.base_url = ""
    settings.asr.frontier_fallback = True
    app = _app(settings)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await _post(client)

    assert response.status_code == 200
    assert response.json()["text"] == "hello from asr"
    assert len(seen) == 1
    request = seen[0]
    assert request.url.host == "frontier.example"
    assert request.url.path == "/v1/audio/transcriptions"
    assert request.headers["authorization"] == "Bearer sk-frontier-test"
    assert b"RIFF" in request.content


@pytest.mark.asyncio
async def test_frontier_fallback_without_key_is_501(settings, monkeypatch):
    for name in ("DAARI_FRONTIER_API_KEY", "OPENAI_API_KEY", "OPENROUTER_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    settings.frontier.enabled = True
    settings.asr.frontier_fallback = True

    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("must not upload without a frontier key")

    _patch_upstream(monkeypatch, handler)
    app = _app(settings)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await _post(client)

    assert response.status_code == 501


@pytest.mark.asyncio
async def test_frontier_disabled_ignores_fallback_flag(settings, monkeypatch):
    monkeypatch.setenv("DAARI_FRONTIER_API_KEY", "sk-frontier-test")
    settings.frontier.enabled = False
    settings.asr.frontier_fallback = True

    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("must not upload when frontier is disabled")

    _patch_upstream(monkeypatch, handler)
    app = _app(settings)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await _post(client)

    assert response.status_code == 501


def test_frontier_fallback_uses_first_provider_base(settings, monkeypatch):
    for name in ("DAARI_FRONTIER_API_KEY", "OPENAI_API_KEY", "OPENROUTER_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    settings.frontier.enabled = True
    settings.frontier.providers = [
        FrontierProviderConfig(
            id="custom",
            base_url="https://asr-frontier.example/v1",
            model="whisper-1",
            keys=["provider-key"],
        )
    ]
    settings.asr.frontier_fallback = True
    target = resolve_asr_target(settings)
    assert target is not None
    assert target.base_url == "https://asr-frontier.example/v1"
    assert target.api_key == "provider-key"
    assert target.via == "frontier"


@pytest.mark.asyncio
async def test_auth_required_like_chat(settings, monkeypatch):
    seen: list[httpx.Request] = []
    _patch_upstream(monkeypatch, _ok_handler(seen))
    settings.server.api_key = "master-secret"
    settings.asr.base_url = "http://asr.local/v1"
    app = _app(settings)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        denied = await _post(client)
        allowed = await _post(client, headers={"Authorization": "Bearer master-secret"})

    assert denied.status_code == 401
    assert denied.json()["error"]["type"] == "authentication_error"
    assert allowed.status_code == 200


@pytest.mark.asyncio
async def test_transcription_counts_against_request_quota(settings, tmp_path, monkeypatch):
    seen: list[httpx.Request] = []
    _patch_upstream(monkeypatch, _ok_handler(seen))
    settings.server.api_key = "master"
    settings.server.virtual_keys.path = str(tmp_path / "vk.sqlite3")
    settings.usage.path = str(tmp_path / "usage.sqlite3")
    settings.asr.base_url = "http://asr.local/v1"
    store = VirtualKeyStore(settings.virtual_keys_path)
    app = _app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    app.state.virtual_key_store = store
    app.state.ctx.virtual_key_store = store
    ledger = UsageLedger(tmp_path / "usage.sqlite3")
    app.state.ctx.router.usage_ledger = ledger
    key = store.create(
        "a",
        client_id="key-a",
        budget_windows=[BudgetWindow("day", 0.0, max_requests=1)],
    )
    headers = {"Authorization": f"Bearer {key.plaintext}"}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        first = await _post(client, headers=headers)
        second = await _post(client, headers=headers)

    assert first.status_code == 200
    assert ledger.request_count_for_client("key-a") == 1
    assert second.status_code == 402
    assert second.json()["error"]["quota"] == "requests"


@pytest.mark.asyncio
async def test_rate_limit_applies_to_transcriptions(settings, monkeypatch):
    seen: list[httpx.Request] = []
    _patch_upstream(monkeypatch, _ok_handler(seen))
    settings.rate_limit.rpm = 1
    settings.asr.base_url = "http://asr.local/v1"
    app = _app(settings)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        first = await _post(client)
        second = await _post(client)

    assert first.status_code == 200
    assert second.status_code == 429
    assert second.json()["error"]["type"] == "rate_limit_error"


@pytest.mark.asyncio
async def test_non_json_response_format_is_400(settings, monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("must not upload unsupported formats")

    _patch_upstream(monkeypatch, handler)
    settings.asr.base_url = "http://asr.local/v1"
    app = _app(settings)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await _post(client, data=_form(response_format="srt"))

    assert response.status_code == 400
    assert "json" in response.json()["error"]["message"]


@pytest.mark.asyncio
async def test_missing_model_is_400(settings, monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("must not upload without a model")

    _patch_upstream(monkeypatch, handler)
    settings.asr.base_url = "http://asr.local/v1"
    app = _app(settings)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await _post(client, data={"response_format": "json"})

    assert response.status_code == 400
    assert "model" in response.json()["error"]["message"]


@pytest.mark.asyncio
async def test_upstream_failure_is_502(settings, monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "boom"})

    _patch_upstream(monkeypatch, handler)
    settings.asr.base_url = "http://asr.local/v1"
    app = _app(settings)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await _post(client)

    assert response.status_code == 502
    assert response.json()["error"]["type"] == "asr_upstream_error"
    assert "boom" not in response.json()["error"]["message"]
