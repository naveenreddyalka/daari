"""POST /v1/decisions — OpenAI Decisions beta on local models + gpt-6-luna (#1474)."""

from __future__ import annotations

import json

import httpx
import pytest
from httpx import ASGITransport, AsyncClient

from daari.auth.rate_families import rate_limit_family
from daari.auth.virtual_keys import VirtualKeyStore
from daari.config.settings import FrontierProviderConfig, Settings
from daari.observability.metrics import Metrics
from daari.pricing import cost_usd, matching_model_key, resolve_price
from daari.router.capabilities import known_model_capabilities
from daari.router.param_compat import lookup_frontier_param_compat
from daari.router.router import AppContext
from daari.server.app import create_app


def _patch_local(monkeypatch, handler):
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


def _patch_frontier(monkeypatch, handler):
    from daari.gateway import decisions

    decisions._http = None
    real = httpx.AsyncClient

    class Patched(real):
        def __init__(self, *args, **kwargs):
            if kwargs.get("transport") is None:
                kwargs["transport"] = httpx.MockTransport(handler)
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", Patched)
    monkeypatch.setattr("daari.gateway.decisions.httpx.AsyncClient", Patched)


def _app(settings):
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    return app


_SYSTEMONE_OK = {
    "model": "nimble",
    "answers": {
        "department": {
            "type": "choice",
            "choice": "billing",
            "probabilities": {
                "billing": 0.95,
                "technical": 0.02,
                "shipping": 0.01,
                "other": 0.02,
            },
            "confidence": 0.93,
        }
    },
    "usage": {"input_tokens": 120, "output_tokens": 1},
}

_OPENAI_OK = {
    "id": "dec_test",
    "model": "gpt-6-luna",
    "answers": [
        {
            "type": "choice",
            "name": "department",
            "choice": "billing",
            "probabilities": [
                {"value": "billing", "probability": 0.95},
                {"value": "technical", "probability": 0.02},
            ],
            "confidence": 0.93,
        }
    ],
    "usage": {"input_tokens": 80, "output_tokens": 0},
}

_BODY = {
    "model": "nimble",
    "input": "I was charged twice for my order.",
    "questions": [
        {
            "type": "choice",
            "name": "department",
            "instructions": "Which department should handle this complaint?",
            "choices": [
                {"value": "billing", "description": "Payments and refunds"},
                {"value": "technical", "description": "Product problems"},
                {"value": "shipping", "description": "Delivery"},
                {"value": "other", "description": "Everything else"},
            ],
        }
    ],
}


def test_openapi_lists_decisions(settings):
    schema = create_app(settings).openapi()
    assert "/v1/decisions" in schema["paths"]
    assert "post" in schema["paths"]["/v1/decisions"]


def test_rate_family_maps_decisions():
    assert rate_limit_family("/v1/decisions") == "decisions"
    assert rate_limit_family("/v1/decisions/") == "decisions"


def test_gpt_6_luna_pricing_capabilities_param_compat():
    settings = Settings()
    price = resolve_price("gpt-6-luna", settings.pricing, fallback_per_1k=0.002)
    assert price.is_fallback is False
    assert price.input_per_1m == pytest.approx(0.10)
    assert price.output_per_1m == pytest.approx(0.0)
    assert matching_model_key("openai.gpt-6-luna", settings.pricing.models) == "gpt-6-luna"
    assert matching_model_key("gpt-6-luna-20261006", settings.pricing.models) == "gpt-6-luna"
    # Sibling gpt-5.6-luna keeps its own rates.
    sibling = resolve_price("gpt-5.6-luna", settings.pricing, fallback_per_1k=0.002)
    assert sibling.input_per_1m == pytest.approx(0.20)
    usd = cost_usd(
        "gpt-6-luna",
        input_tokens=1_000_000,
        output_tokens=1000,
        pricing=settings.pricing,
        fallback_per_1k=0.002,
    )
    assert usd == pytest.approx(0.10)
    caps = known_model_capabilities("gpt-6-luna")
    assert "vision" in caps
    assert lookup_frontier_param_compat("gpt-6-luna") is not None
    assert lookup_frontier_param_compat("openai.gpt-6-luna") is not None


@pytest.mark.asyncio
async def test_malformed_body_returns_400(settings):
    app = _app(settings)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/v1/decisions", json={"model": "nimble"})

    assert response.status_code == 400
    assert response.json()["error"]["type"] == "invalid_request"


@pytest.mark.asyncio
async def test_local_model_proxies_systemone_and_shapes_openai(settings, monkeypatch):
    seen: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append({"url": str(request.url), "body": json.loads(request.read())})
        return httpx.Response(200, json=_SYSTEMONE_OK)

    _patch_local(monkeypatch, handler)
    settings.ollama.base_url = "http://ollama.local:11434"
    app = _app(settings)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/v1/decisions", json=_BODY)

    assert response.status_code == 200
    body = response.json()
    assert body["model"] == "nimble"
    assert isinstance(body["answers"], list)
    assert body["answers"][0]["name"] == "department"
    assert body["answers"][0]["choice"] == "billing"
    assert body["answers"][0]["probabilities"][0]["value"] == "billing"
    meta = body["daari_meta"]
    assert meta["tier"] == "decisions"
    assert meta["executor"] == "ollama"
    assert response.headers.get("x-daari-tier") == "decisions"
    assert len(seen) == 1
    assert seen[0]["url"] == "http://ollama.local:11434/v1/systemone"
    payload = seen[0]["body"]
    assert payload["model"] == "nimble"
    assert payload["state"] == _BODY["input"]
    assert "department" in payload["questions"]
    assert payload["questions"]["department"]["type"] == "choice"
    assert payload["questions"]["department"]["criteria"]["billing"] == "Payments and refunds"


@pytest.mark.asyncio
async def test_default_model_uses_local_when_configured(settings, monkeypatch):
    seen: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.read()))
        return httpx.Response(200, json=_SYSTEMONE_OK)

    _patch_local(monkeypatch, handler)
    settings.ollama.base_url = "http://ollama.local:11434"
    app = _app(settings)
    body = {k: v for k, v in _BODY.items() if k != "model"}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/v1/decisions", json=body)

    assert response.status_code == 200
    assert seen[0]["model"] == "nimble"


@pytest.mark.asyncio
async def test_forwards_images_on_local_path(settings, monkeypatch):
    seen: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.read()))
        return httpx.Response(200, json=_SYSTEMONE_OK)

    _patch_local(monkeypatch, handler)
    settings.ollama.base_url = "http://ollama.local:11434"
    app = _app(settings)
    body = {
        "model": "clef",
        "input": [
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": "Inspect this photo."},
                    {
                        "type": "input_image",
                        "image_url": "data:image/png;base64,aGVsbG8=",
                    },
                ],
            }
        ],
        "questions": [
            {
                "type": "predicate",
                "name": "visible_damage",
                "instructions": "Is there visible damage?",
            }
        ],
    }

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/v1/decisions", json=body)

    assert response.status_code == 200
    assert seen[0]["images"] == ["aGVsbG8="]
    assert "Inspect this photo." in seen[0]["state"]
    assert seen[0]["questions"]["visible_damage"]["type"] == "boolean"


@pytest.mark.asyncio
async def test_gpt_6_luna_passthrough_to_frontier(settings, monkeypatch):
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=_OPENAI_OK)

    _patch_frontier(monkeypatch, handler)
    settings.frontier.enabled = True
    settings.frontier.providers = [
        FrontierProviderConfig(
            id="openai",
            base_url="https://api.openai.com/v1",
            model="gpt-4o",
            keys=["sk-test"],
        )
    ]
    app = _app(settings)
    body = {**_BODY, "model": "gpt-6-luna"}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/v1/decisions", json=body)

    assert response.status_code == 200
    assert response.json()["answers"][0]["choice"] == "billing"
    assert response.json()["daari_meta"]["tier"] == "decisions"
    assert response.json()["daari_meta"]["executor"] == "frontier"
    assert len(seen) == 1
    assert str(seen[0].url) == "https://api.openai.com/v1/decisions"
    assert seen[0].headers["authorization"] == "Bearer sk-test"
    payload = json.loads(seen[0].read())
    assert payload["model"] == "gpt-6-luna"
    assert payload["input"] == _BODY["input"]


@pytest.mark.asyncio
async def test_no_frontier_blocks_gpt_6_luna(settings, monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("frontier must not be called")

    _patch_frontier(monkeypatch, handler)
    settings.frontier.enabled = True
    settings.frontier.providers = [
        FrontierProviderConfig(
            id="openai",
            base_url="https://api.openai.com/v1",
            model="gpt-4o",
            keys=["sk-test"],
        )
    ]
    app = _app(settings)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/decisions",
            json={**_BODY, "model": "gpt-6-luna"},
            headers={"X-Daari-No-Frontier": "true"},
        )

    assert response.status_code == 403
    assert response.json()["error"]["type"] == "frontier_not_allowed"


@pytest.mark.asyncio
async def test_records_usage_ledger_and_metrics_local(settings, monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_SYSTEMONE_OK)

    _patch_local(monkeypatch, handler)
    settings.ollama.base_url = "http://ollama.local:11434"
    app = _app(settings)
    app.state.ctx.metrics = Metrics()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/v1/decisions", json=_BODY)

    assert response.status_code == 200
    from daari.observability.prometheus import render_prometheus

    text = render_prometheus(app.state.ctx.metrics)
    assert 'modality="decisions"' in text
    blob = json.dumps(app.state.ctx.router.usage_ledger.report(days=1))
    assert "decisions" in blob


@pytest.mark.asyncio
async def test_auth_required_when_api_key_set(settings, monkeypatch, tmp_path):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_SYSTEMONE_OK)

    _patch_local(monkeypatch, handler)
    settings.server.api_key = "master"
    settings.server.virtual_keys.path = str(tmp_path / "vk.sqlite3")
    store = VirtualKeyStore(settings.virtual_keys_path)
    key = store.create("bot", client_id="bot-1")
    app = _app(settings)
    app.state.virtual_key_store = store
    app.state.ctx.virtual_key_store = store

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        unauth = await client.post("/v1/decisions", json=_BODY)
        ok = await client.post(
            "/v1/decisions",
            json=_BODY,
            headers={"Authorization": f"Bearer {key.plaintext}"},
        )

    assert unauth.status_code == 401
    assert ok.status_code == 200
