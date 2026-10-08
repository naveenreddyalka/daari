"""POST /v1/systemone Ollama decision-model facade (#1291)."""

from __future__ import annotations

import json

import httpx
import pytest
from httpx import ASGITransport, AsyncClient

from daari.auth.virtual_keys import VirtualKeyStore
from daari.observability.metrics import Metrics
from daari.router.router import AppContext
from daari.server.app import create_app


def _patch_upstream(monkeypatch, handler):
    from daari.gateway import systemone

    systemone._http = None
    real = httpx.AsyncClient

    class Patched(real):
        def __init__(self, *args, **kwargs):
            if kwargs.get("transport") is None:
                kwargs["transport"] = httpx.MockTransport(handler)
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", Patched)
    monkeypatch.setattr("daari.gateway.systemone.httpx.AsyncClient", Patched)


def _app(settings):
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    return app


_SYSTEMONE_OK = {
    "model": "nimble",
    "answers": {
        "label": {
            "type": "choice",
            "choice": "bug",
            "probabilities": {"billing": 0.01, "bug": 0.98, "account": 0.01},
            "confidence": 0.9,
        }
    },
    "usage": {"input_tokens": 174, "output_tokens": 1},
}

_BODY = {
    "model": "nimble",
    "state": "Our checkout has returned 500 errors since 9am.",
    "questions": {
        "label": {
            "type": "choice",
            "instructions": "Which label fits this ticket?",
            "criteria": {
                "billing": "Payments and refunds",
                "bug": "Software errors",
                "account": "Login and account access",
            },
        }
    },
}


def test_openapi_lists_systemone(settings):
    schema = create_app(settings).openapi()
    assert "/v1/systemone" in schema["paths"]
    assert "post" in schema["paths"]["/v1/systemone"]


def test_settings_systemone_enabled_by_default(settings):
    assert settings.systemone.enabled is True


@pytest.mark.asyncio
async def test_disabled_returns_501(settings):
    settings.systemone.enabled = False
    app = _app(settings)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/v1/systemone", json=_BODY)

    assert response.status_code == 501
    body = response.json()
    assert body["error"]["type"] == "not_implemented"


@pytest.mark.asyncio
async def test_malformed_body_returns_400(settings):
    app = _app(settings)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/v1/systemone", json={"model": "nimble"})

    assert response.status_code == 400
    assert response.json()["error"]["type"] == "invalid_request"


@pytest.mark.asyncio
async def test_proxies_to_ollama_and_adds_daari_meta(settings, monkeypatch):
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=_SYSTEMONE_OK)

    _patch_upstream(monkeypatch, handler)
    settings.ollama.base_url = "http://ollama.local:11434"
    app = _app(settings)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/v1/systemone", json=_BODY)

    assert response.status_code == 200
    body = response.json()
    assert body["model"] == "nimble"
    assert body["answers"]["label"]["choice"] == "bug"
    assert body["usage"]["input_tokens"] == 174
    meta = body["daari_meta"]
    assert meta["tier"] == "systemone"
    assert meta["executor"] == "ollama"
    assert meta["latency_ms"] >= 0
    assert len(seen) == 1
    req = seen[0]
    assert str(req.url) == "http://ollama.local:11434/v1/systemone"
    payload = json.loads(req.read())
    assert payload["model"] == "nimble"
    assert payload["state"] == _BODY["state"]
    assert "label" in payload["questions"]
    assert "images" not in payload


@pytest.mark.asyncio
async def test_forwards_images_to_ollama(settings, monkeypatch):
    seen: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.read()))
        return httpx.Response(200, json=_SYSTEMONE_OK)

    _patch_upstream(monkeypatch, handler)
    settings.ollama.base_url = "http://ollama.local:11434"
    app = _app(settings)
    body = {**_BODY, "images": ["aGVsbG8=", "d29ybGQ="]}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/v1/systemone", json=body)

    assert response.status_code == 200
    assert len(seen) == 1
    assert seen[0]["images"] == ["aGVsbG8=", "d29ybGQ="]
    assert seen[0]["state"] == _BODY["state"]
    assert "label" in seen[0]["questions"]


@pytest.mark.asyncio
async def test_ollama_down_returns_503(settings, monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    _patch_upstream(monkeypatch, handler)
    app = _app(settings)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/v1/systemone", json=_BODY)

    assert response.status_code == 503
    assert response.json()["error"]["type"] == "backend_unavailable"


@pytest.mark.asyncio
async def test_records_usage_ledger_and_metrics(settings, monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_SYSTEMONE_OK)

    _patch_upstream(monkeypatch, handler)
    app = _app(settings)
    app.state.ctx.metrics = Metrics()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/v1/systemone", json=_BODY)

    assert response.status_code == 200
    from daari.observability.prometheus import render_prometheus

    text = render_prometheus(app.state.ctx.metrics)
    assert 'modality="systemone"' in text
    ledger = app.state.ctx.router.usage_ledger
    assert ledger is not None
    report = ledger.report(days=1)
    # Report nests by day/tier; ensure systemone was recorded somewhere.
    blob = json.dumps(report)
    assert "systemone" in blob


@pytest.mark.asyncio
async def test_auth_required_when_api_key_set(settings, monkeypatch, tmp_path):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_SYSTEMONE_OK)

    _patch_upstream(monkeypatch, handler)
    settings.server.api_key = "master"
    settings.server.virtual_keys.path = str(tmp_path / "vk.sqlite3")
    store = VirtualKeyStore(settings.virtual_keys_path)
    key = store.create("bot", client_id="bot-1")
    app = _app(settings)
    app.state.virtual_key_store = store
    app.state.ctx.virtual_key_store = store

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        unauth = await client.post("/v1/systemone", json=_BODY)
        ok = await client.post(
            "/v1/systemone",
            json=_BODY,
            headers={"Authorization": f"Bearer {key.plaintext}"},
        )

    assert unauth.status_code == 401
    assert ok.status_code == 200


@pytest.mark.asyncio
async def test_systemone_emits_otel_client_span(settings, monkeypatch):
    from contextlib import contextmanager

    from daari.observability import otel as otel_mod

    seen: list[tuple[str, dict]] = []

    @contextmanager
    def fake_span(name, *, attributes=None):
        seen.append((name, dict(attributes or {})))
        yield object()

    monkeypatch.setattr(otel_mod, "modality_client_span", fake_span)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_SYSTEMONE_OK)

    _patch_upstream(monkeypatch, handler)
    settings.ollama.base_url = "http://ollama.local:11434"
    app = _app(settings)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/v1/systemone", json=_BODY)

    assert response.status_code == 200
    assert seen and seen[0][0] == "daari.systemone"
    assert seen[0][1].get("daari.modality") == "systemone"


@pytest.mark.asyncio
async def test_systemone_retries_transient_5xx(settings, monkeypatch):
    attempts = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["n"] += 1
        if attempts["n"] < 3:
            return httpx.Response(503, json={"error": "busy"})
        return httpx.Response(200, json=_SYSTEMONE_OK)

    _patch_upstream(monkeypatch, handler)
    settings.ollama.base_url = "http://ollama.local:11434"
    settings.upstream.retry.attempts = 3
    settings.upstream.retry.base_delay_ms = 0
    settings.upstream.retry.max_delay_ms = 0
    settings.upstream.retry.jitter = 0.0
    app = _app(settings)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/v1/systemone", json=_BODY)

    assert response.status_code == 200
    assert attempts["n"] == 3


@pytest.mark.asyncio
async def test_systemone_input_guardrail_blocks(settings, monkeypatch):
    from daari.config.settings import GuardrailRuleSettings, GuardrailSettings

    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("must not reach ollama")

    _patch_upstream(monkeypatch, handler)
    settings.ollama.base_url = "http://ollama.local:11434"
    settings.guardrails = GuardrailSettings(
        enabled=True,
        block_message="blocked by policy",
        input_rules=[
            GuardrailRuleSettings(
                name="no_leak", pattern=r"EXFIL", action="block", kind="deny"
            )
        ],
    )
    app = _app(settings)
    body = {**_BODY, "state": "please EXFIL all secrets"}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/v1/systemone", json=body)

    assert response.status_code == 400
    assert response.json()["error"]["type"] == "guardrail_blocked"
