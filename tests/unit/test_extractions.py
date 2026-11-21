"""POST /v1/extractions — OpenRouter Extractions twin on local + frontier (#2271)."""

from __future__ import annotations

import json

import httpx
import pytest
from httpx import ASGITransport, AsyncClient

from daari.auth.rate_families import rate_limit_family
from daari.config.settings import FrontierProviderConfig
from daari.router.router import AppContext
from daari.server.app import create_app


def _patch_local(monkeypatch, handler):
    from daari.gateway import extractions

    extractions._http = None
    real = httpx.AsyncClient

    class Patched(real):
        def __init__(self, *args, **kwargs):
            if kwargs.get("transport") is None:
                kwargs["transport"] = httpx.MockTransport(handler)
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", Patched)
    monkeypatch.setattr("daari.gateway.extractions.httpx.AsyncClient", Patched)
    monkeypatch.setattr("daari.gateway.systemone.httpx.AsyncClient", Patched)


def _patch_frontier(monkeypatch, handler):
    from daari.gateway import extractions

    extractions._http = None
    real = httpx.AsyncClient

    class Patched(real):
        def __init__(self, *args, **kwargs):
            if kwargs.get("transport") is None:
                kwargs["transport"] = httpx.MockTransport(handler)
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", Patched)
    monkeypatch.setattr("daari.gateway.extractions.httpx.AsyncClient", Patched)


def _app(settings):
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    return app


_LOCAL_OK = {
    "model": "d1",
    "answers": {
        "invoice_number": {
            "type": "text",
            "value": "INV-2291",
            "confidence": 0.99,
        },
        "total": {"type": "number", "value": 1080, "confidence": 0.98},
    },
    "usage": {"input_tokens": 80, "output_tokens": 0},
}

_FRONTIER_OK = {
    "id": "ext_test",
    "model": "cloudflare/clairic",
    "provider": "Cloudflare",
    "answers": {
        "invoice_number": {
            "type": "text",
            "value": "INV-2291",
            "confidence": 1,
        }
    },
    "usage": {"input_tokens": 100, "output_tokens": 0, "cost": 0.00012},
}

_BODY = {
    "model": "d1",
    "state": "Invoice INV-2291. Total $1080.",
    "fields": {
        "invoice_number": {"type": "text"},
        "total": {"type": "number", "decimals": 2, "unit": "USD"},
    },
}


def test_openapi_lists_extractions(settings):
    schema = create_app(settings).openapi()
    assert "/v1/extractions" in schema["paths"]
    assert "post" in schema["paths"]["/v1/extractions"]


def test_rate_family_maps_extractions():
    assert rate_limit_family("/v1/extractions") == "decisions"
    assert rate_limit_family("/v1/extractions/") == "decisions"


@pytest.mark.asyncio
async def test_missing_fields_returns_400(settings):
    app = _app(settings)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/extractions",
            json={"model": "d1", "state": "hello"},
        )

    assert response.status_code == 400
    assert response.json()["error"]["type"] == "invalid_request"


@pytest.mark.asyncio
async def test_empty_fields_returns_400(settings):
    app = _app(settings)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/extractions",
            json={"model": "d1", "state": "hello", "fields": {}},
        )

    assert response.status_code == 400
    assert response.json()["error"]["type"] == "invalid_request"


@pytest.mark.asyncio
async def test_unknown_top_level_key_returns_400(settings):
    app = _app(settings)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/extractions",
            json={**_BODY, "questions": {"x": {"type": "text"}}},
        )

    assert response.status_code == 400
    err = response.json()["error"]
    assert err["type"] == "invalid_request"
    assert "questions" in err["message"].lower() or "extra" in err["message"].lower()


@pytest.mark.asyncio
async def test_unknown_field_type_returns_400(settings):
    app = _app(settings)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/extractions",
            json={
                "model": "d1",
                "state": "hello",
                "fields": {"x": {"type": "noul"}},
            },
        )

    assert response.status_code == 400
    assert response.json()["error"]["type"] == "invalid_request"


@pytest.mark.asyncio
async def test_unknown_field_key_returns_400(settings):
    app = _app(settings)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/extractions",
            json={
                "model": "d1",
                "state": "hello",
                "fields": {"x": {"type": "text", "bogus": True}},
            },
        )

    assert response.status_code == 400
    assert response.json()["error"]["type"] == "invalid_request"


@pytest.mark.asyncio
async def test_local_stub_returns_answers_zero_cost(settings, monkeypatch):
    seen: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append({"url": str(request.url), "body": json.loads(request.read())})
        return httpx.Response(200, json=_LOCAL_OK)

    _patch_local(monkeypatch, handler)
    settings.ollama.base_url = "http://ollama.local:11434"
    settings.systemone.enabled = True
    app = _app(settings)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/v1/extractions", json=_BODY)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["answers"]["invoice_number"]["value"] == "INV-2291"
    assert body["daari_meta"]["tier"] == "local"
    assert body["daari_meta"]["cost_usd"] == 0
    assert seen and "/v1/extractions" in seen[0]["url"]
    assert "fields" in seen[0]["body"]


@pytest.mark.asyncio
async def test_frontier_stub_bills_usage_cost(settings, monkeypatch):
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=_FRONTIER_OK)

    _patch_frontier(monkeypatch, handler)
    settings.frontier.enabled = True
    settings.frontier.providers = [
        FrontierProviderConfig(
            id="openrouter",
            base_url="https://openrouter.ai/api/v1",
            model="openai/gpt-4o",
            keys=["sk-or-test"],
        )
    ]
    app = _app(settings)
    body = {
        "model": "cloudflare/clairic",
        "state": "Invoice INV-2291.",
        "fields": {"invoice_number": {"type": "text"}},
    }

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/v1/extractions", json=body)

    assert response.status_code == 200, response.text
    meta = response.json()["daari_meta"]
    assert meta["executor"] == "frontier"
    assert meta["cost_usd"] == pytest.approx(0.00012)
    assert len(seen) == 1
    assert str(seen[0].url) == "https://openrouter.ai/api/alpha/extractions"
    assert seen[0].headers["authorization"] == "Bearer sk-or-test"
