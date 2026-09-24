"""Local-first POST /v1/audio/transcriptions (#715)."""

from __future__ import annotations

import time

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


@pytest.mark.asyncio
async def test_transcription_honors_model_allowlist(settings, tmp_path, monkeypatch):
    seen: list[httpx.Request] = []
    _patch_upstream(monkeypatch, _ok_handler(seen))
    settings.server.api_key = "master"
    settings.server.virtual_keys.path = str(tmp_path / "vk.sqlite3")
    settings.asr.base_url = "http://asr.local/v1"
    settings.asr.model = ""
    store = VirtualKeyStore(settings.virtual_keys_path)
    locked = store.create("locked", allowed_models=["ggml-base"])
    open_key = store.create("open")
    team = store.create_team("eng", allowed_models=["ggml-base"])
    member = store.create("member", team="eng")
    app = _app(settings)
    app.state.virtual_key_store = store
    app.state.ctx.virtual_key_store = store

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        denied = await _post(
            client,
            headers={"Authorization": f"Bearer {locked.plaintext}"},
            data=_form("whisper-1"),
        )
        assert denied.status_code == 403
        assert denied.json()["error"]["type"] == "model_not_allowed"
        assert "whisper-1" in denied.json()["error"]["message"]
        assert seen == []

        allowed = await _post(
            client,
            headers={"Authorization": f"Bearer {locked.plaintext}"},
            data=_form("ggml-base"),
        )
        assert allowed.status_code == 200, allowed.text
        assert len(seen) == 1

        team_denied = await _post(
            client,
            headers={"Authorization": f"Bearer {member.plaintext}"},
            data=_form("whisper-1"),
        )
        assert team_denied.status_code == 403
        assert len(seen) == 1

        unrestricted = await _post(
            client,
            headers={"Authorization": f"Bearer {open_key.plaintext}"},
            data=_form("whisper-1"),
        )
        assert unrestricted.status_code == 200, unrestricted.text
        assert len(seen) == 2

    settings.asr.model = "whisper-1"
    override_app = _app(settings)
    override_app.state.virtual_key_store = store
    override_app.state.ctx.virtual_key_store = store
    before = len(seen)
    async with AsyncClient(
        transport=ASGITransport(app=override_app), base_url="http://test"
    ) as client:
        overridden = await _post(
            client,
            headers={"Authorization": f"Bearer {locked.plaintext}"},
            data=_form("ggml-base"),
        )
    assert overridden.status_code == 403
    assert "whisper-1" in overridden.json()["error"]["message"]
    assert len(seen) == before
    assert team.allowed_models == ("ggml-base",)


def _spend_rows(app):
    ledger = app.state.ctx.router.spend_ledger
    return list(ledger.iter_rows(since="2000-01-01T00:00:00+00:00"))


def _enable_spend(settings, tmp_path):
    settings.usage.spend.enabled = True
    settings.usage.spend.path = str(tmp_path / "spend.sqlite3")


@pytest.mark.asyncio
async def test_transcription_spend_rows_distinguish_local_and_frontier(
    settings, tmp_path, monkeypatch
):
    """Chargeback export tags local ASR vs frontier fallback (#751)."""
    seen: list[httpx.Request] = []
    _patch_upstream(monkeypatch, _ok_handler(seen))
    _enable_spend(settings, tmp_path)
    settings.server.api_key = "master"
    settings.server.virtual_keys.path = str(tmp_path / "vk.sqlite3")
    settings.asr.base_url = "http://asr.local/v1"
    settings.asr.model = "ggml-base"
    store = VirtualKeyStore(settings.virtual_keys_path)
    key = store.create("bot", client_id="client-bot", team="eng")
    app = _app(settings)
    app.state.virtual_key_store = store
    app.state.ctx.virtual_key_store = store
    headers = {"Authorization": f"Bearer {key.plaintext}"}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        local = await _post(client, headers=headers)
    assert local.status_code == 200, local.text
    local_rows = _spend_rows(app)
    assert len(local_rows) == 1
    assert local_rows[0]["tier"] == "asr"
    assert local_rows[0]["key_id"] == key.key.key_id
    assert local_rows[0]["team_id"] == key.key.team_id
    assert local_rows[0]["model"] == "ggml-base"

    settings.asr.base_url = ""
    settings.asr.frontier_fallback = True
    settings.frontier.enabled = True
    settings.frontier.base_url = "https://frontier.example/v1"
    monkeypatch.setenv("DAARI_FRONTIER_API_KEY", "sk-frontier-test")
    frontier_app = _app(settings)
    frontier_app.state.virtual_key_store = store
    frontier_app.state.ctx.virtual_key_store = store
    async with AsyncClient(
        transport=ASGITransport(app=frontier_app), base_url="http://test"
    ) as client:
        frontier = await _post(client, headers=headers)
    assert frontier.status_code == 200, frontier.text
    frontier_rows = [row for row in _spend_rows(frontier_app) if row["tier"] == "L6"]
    assert len(frontier_rows) == 1
    assert frontier_rows[0]["key_id"] == key.key.key_id
    assert frontier_rows[0]["team_id"] == key.key.team_id
    assert {local_rows[0]["tier"], frontier_rows[0]["tier"]} == {"asr", "L6"}


@pytest.mark.asyncio
async def test_transcription_denials_do_not_write_spend_rows(settings, tmp_path, monkeypatch):
    """403 allowlist and 501 unconfigured responses are not chargeback rows (#751)."""

    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("must not upload audio")

    _patch_upstream(monkeypatch, handler)
    _enable_spend(settings, tmp_path)
    settings.server.api_key = "master"
    settings.server.virtual_keys.path = str(tmp_path / "vk.sqlite3")
    store = VirtualKeyStore(settings.virtual_keys_path)
    locked = store.create("locked", allowed_models=["ggml-base"])
    app = _app(settings)
    app.state.virtual_key_store = store
    app.state.ctx.virtual_key_store = store

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        missing = await _post(client, headers={"Authorization": f"Bearer {locked.plaintext}"})
    assert missing.status_code == 501
    assert _spend_rows(app) == []

    settings.asr.base_url = "http://asr.local/v1"
    denied_app = _app(settings)
    denied_app.state.virtual_key_store = store
    denied_app.state.ctx.virtual_key_store = store
    async with AsyncClient(
        transport=ASGITransport(app=denied_app), base_url="http://test"
    ) as client:
        denied = await _post(
            client,
            headers={"Authorization": f"Bearer {locked.plaintext}"},
            data=_form("whisper-1"),
        )
    assert denied.status_code == 403
    assert denied.json()["error"]["type"] == "model_not_allowed"
    assert _spend_rows(denied_app) == []


def _sleeping_handler(seen: list[httpx.Request]):
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        time.sleep(0.02)
        return httpx.Response(200, json={"text": "hello from asr"})

    return handler


@pytest.mark.asyncio
async def test_local_and_frontier_transcriptions_record_latency(settings, monkeypatch):
    seen: list[httpx.Request] = []
    _patch_upstream(monkeypatch, _sleeping_handler(seen))
    settings.asr.base_url = "http://asr.local/v1"
    settings.asr.model = "ggml-base"
    app = _app(settings)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await _post(client)
    assert response.status_code == 200, response.text
    local = app.state.ctx.metrics.snapshot(include_histograms=True)["tiers"]["asr"]
    assert local["total_latency_ms"] > 0
    assert sum(local["latency_buckets"].values()) > 0

    monkeypatch.setenv("DAARI_FRONTIER_API_KEY", "sk-frontier-test")
    settings.frontier.enabled = True
    settings.frontier.base_url = "https://frontier.example/v1"
    settings.asr.base_url = ""
    settings.asr.frontier_fallback = True
    frontier_app = _app(settings)
    async with AsyncClient(
        transport=ASGITransport(app=frontier_app), base_url="http://test"
    ) as client:
        response = await _post(client)
    assert response.status_code == 200, response.text
    frontier = frontier_app.state.ctx.metrics.snapshot(include_histograms=True)["tiers"]["L6"]
    assert frontier["total_latency_ms"] > 0
    assert sum(frontier["latency_buckets"].values()) > 0


@pytest.mark.asyncio
async def test_frontier_fallback_no_frontier_key_never_uploads(settings, tmp_path, monkeypatch):
    """Virtual-key no_frontier must not upload audio on ASR frontier fallback (#1061)."""

    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError(f"must not upload audio to {request.url}")

    _patch_upstream(monkeypatch, handler)
    settings.asr.base_url = ""
    settings.asr.frontier_fallback = True
    settings.frontier.enabled = True
    settings.frontier.providers = [
        FrontierProviderConfig(
            id="openai",
            base_url="https://api.openai.com/v1",
            model="whisper-1",
            keys=["sk-test"],
        )
    ]
    settings.server.api_key = "master"
    settings.server.virtual_keys.path = str(tmp_path / "vk.sqlite3")
    store = VirtualKeyStore(settings.virtual_keys_path)
    locked = store.create("local-only", metadata={"no_frontier": True})
    app = _app(settings)
    app.state.virtual_key_store = store
    app.state.ctx.virtual_key_store = store

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await _post(
            client, headers={"Authorization": f"Bearer {locked.plaintext}"}
        )
    assert response.status_code == 403
    assert response.json()["error"]["type"] == "frontier_not_allowed"


@pytest.mark.asyncio
async def test_frontier_fallback_region_pin_filters_slots(settings, tmp_path, monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError(f"must not upload audio to {request.url}")

    _patch_upstream(monkeypatch, handler)
    settings.asr.base_url = ""
    settings.asr.frontier_fallback = True
    settings.frontier.enabled = True
    settings.frontier.providers = [
        FrontierProviderConfig(
            id="us",
            base_url="https://us.example/v1",
            model="whisper-1",
            keys=["sk-us"],
            region="us",
        )
    ]
    settings.server.api_key = "master"
    settings.server.virtual_keys.path = str(tmp_path / "vk.sqlite3")
    store = VirtualKeyStore(settings.virtual_keys_path)
    pinned = store.create("eu-bot", region_pin="eu")
    app = _app(settings)
    app.state.virtual_key_store = store
    app.state.ctx.virtual_key_store = store

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await _post(
            client, headers={"Authorization": f"Bearer {pinned.plaintext}"}
        )
    assert response.status_code == 400
    assert response.json()["error"]["type"] == "region_unavailable"


@pytest.mark.asyncio
async def test_frontier_fallback_region_pin_uses_matching_slot(settings, tmp_path, monkeypatch):
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.host)
        return httpx.Response(200, json={"text": "eu transcript"})

    _patch_upstream(monkeypatch, handler)
    settings.asr.base_url = ""
    settings.asr.frontier_fallback = True
    settings.frontier.enabled = True
    settings.frontier.providers = [
        FrontierProviderConfig(
            id="us",
            base_url="https://us.example/v1",
            model="whisper-1",
            keys=["sk-us"],
            region="us",
        ),
        FrontierProviderConfig(
            id="eu",
            base_url="https://eu.example/v1",
            model="whisper-1",
            keys=["sk-eu"],
            region="eu",
        ),
    ]
    settings.server.api_key = "master"
    settings.server.virtual_keys.path = str(tmp_path / "vk.sqlite3")
    store = VirtualKeyStore(settings.virtual_keys_path)
    pinned = store.create("eu-bot", region_pin="eu")
    app = _app(settings)
    app.state.virtual_key_store = store
    app.state.ctx.virtual_key_store = store

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await _post(
            client, headers={"Authorization": f"Bearer {pinned.plaintext}"}
        )
    assert response.status_code == 200, response.text
    assert response.json()["text"] == "eu transcript"
    assert seen == ["eu.example"]


@pytest.mark.asyncio
async def test_frontier_fallback_slot_failover(settings, monkeypatch):
    seen_hosts: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_hosts.append(request.url.host)
        if request.url.host == "primary.example":
            return httpx.Response(503, json={"error": {"type": "busy", "message": "down"}})
        return httpx.Response(200, json={"text": "from secondary"})

    _patch_upstream(monkeypatch, handler)
    settings.asr.base_url = ""
    settings.asr.frontier_fallback = True
    settings.frontier.enabled = True
    settings.frontier.providers = [
        FrontierProviderConfig(
            id="primary",
            base_url="https://primary.example/v1",
            model="whisper-1",
            keys=["sk-a"],
            retry_attempts=1,
        ),
        FrontierProviderConfig(
            id="secondary",
            base_url="https://secondary.example/v1",
            model="whisper-1",
            keys=["sk-b"],
            retry_attempts=1,
        ),
    ]
    app = _app(settings)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await _post(client)
    assert response.status_code == 200, response.text
    assert response.json()["text"] == "from secondary"
    assert seen_hosts[0] == "primary.example"
    assert "secondary.example" in seen_hosts


@pytest.mark.asyncio
async def test_frontier_fallback_unpinned_keeps_first_slot(settings, monkeypatch):
    """Unpinned keys keep today's first-eligible-slot behavior (#1061)."""
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.host)
        return httpx.Response(200, json={"text": "ok"})

    _patch_upstream(monkeypatch, handler)
    settings.asr.base_url = ""
    settings.asr.frontier_fallback = True
    settings.frontier.enabled = True
    settings.frontier.providers = [
        FrontierProviderConfig(
            id="primary",
            base_url="https://primary.example/v1",
            model="whisper-1",
            keys=["sk-a"],
        ),
        FrontierProviderConfig(
            id="secondary",
            base_url="https://secondary.example/v1",
            model="whisper-1",
            keys=["sk-b"],
        ),
    ]
    app = _app(settings)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await _post(client)
    assert response.status_code == 200, response.text
    assert seen == ["primary.example"]
