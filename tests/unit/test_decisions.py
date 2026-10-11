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
    post = schema["paths"]["/v1/decisions"]["post"]
    assert post is not None
    # Decisions is non-streaming; OpenAPI must not advertise a stream parameter.
    params = post.get("parameters") or []
    assert not any(
        isinstance(p, dict) and p.get("name") == "stream" for p in params
    )
    body_schema = (
        ((post.get("requestBody") or {}).get("content") or {})
        .get("application/json", {})
        .get("schema")
        or {}
    )
    props = body_schema.get("properties") or {}
    assert "stream" not in props
    description = (post.get("description") or "").lower()
    assert "stream" not in description or "unsupported" in description


@pytest.mark.asyncio
async def test_stream_true_returns_400(settings, monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("stream=true must not reach upstream")

    _patch_local(monkeypatch, handler)
    settings.ollama.base_url = "http://ollama.local:11434"
    app = _app(settings)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/decisions", json={**_BODY, "stream": True}
        )

    assert response.status_code == 400
    err = response.json()["error"]
    assert err["type"] == "invalid_request"
    assert "stream" in err["message"].lower()


@pytest.mark.asyncio
async def test_stream_false_and_omitted_succeed(settings, monkeypatch):
    seen = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["n"] += 1
        return httpx.Response(200, json=_SYSTEMONE_OK)

    _patch_local(monkeypatch, handler)
    settings.ollama.base_url = "http://ollama.local:11434"
    settings.decisions.cache_enabled = False
    app = _app(settings)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        omitted = await client.post("/v1/decisions", json=_BODY)
        explicit = await client.post(
            "/v1/decisions", json={**_BODY, "stream": False}
        )

    assert omitted.status_code == 200, omitted.text
    assert explicit.status_code == 200, explicit.text
    assert seen["n"] == 2


def test_rate_family_maps_decisions():
    assert rate_limit_family("/v1/decisions") == "decisions"
    assert rate_limit_family("/v1/decisions/") == "decisions"


def test_normalize_decisions_model_aliases():
    from daari.gateway.decisions import normalize_decisions_model

    assert normalize_decisions_model("gpt-6-luna") == "gpt-6-luna"
    assert normalize_decisions_model("gpt-6-luna-decisions") == "gpt-6-luna"
    assert normalize_decisions_model("openai/gpt-6-luna-decisions") == "gpt-6-luna"
    assert normalize_decisions_model("nimble") == "nimble"
    assert normalize_decisions_model("clef-flash") == "clef-flash"
    assert normalize_decisions_model("gpt-4o") is None
    assert normalize_decisions_model("") is None


def test_gpt_6_luna_pricing_capabilities_param_compat():
    settings = Settings()
    price = resolve_price("gpt-6-luna", settings.pricing, fallback_per_1k=0.002)
    assert price.is_fallback is False
    assert price.input_per_1m == pytest.approx(0.10)
    assert price.output_per_1m == pytest.approx(0.50)
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
    assert usd == pytest.approx(0.1005)
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
@pytest.mark.parametrize(
    "alias",
    ["gpt-6-luna", "gpt-6-luna-decisions", "openai/gpt-6-luna-decisions"],
)
async def test_gpt_6_luna_decisions_aliases_normalize_to_frontier(settings, monkeypatch, alias):
    seen: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.read()))
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

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/v1/decisions", json={**_BODY, "model": alias})

    assert response.status_code == 200, response.text
    assert seen and seen[0]["model"] == "gpt-6-luna"
    assert response.json()["daari_meta"]["executor"] == "frontier"


@pytest.mark.asyncio
async def test_unknown_decisions_model_returns_400(settings, monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("must not reach upstream")

    _patch_local(monkeypatch, handler)
    _patch_frontier(monkeypatch, handler)
    settings.ollama.base_url = "http://ollama.local:11434"
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
        response = await client.post("/v1/decisions", json={**_BODY, "model": "gpt-4o"})

    assert response.status_code == 400
    assert response.json()["error"]["type"] == "invalid_request"
    assert "gpt-4o" in response.json()["error"]["message"]


@pytest.mark.asyncio
async def test_gpt_6_luna_decisions_cost_ignores_output_and_cache(settings, monkeypatch):
    billed = {
        **_OPENAI_OK,
        "usage": {
            "input_tokens": 1_000_000,
            "output_tokens": 1_000_000,
            "prompt_tokens_details": {"cached_tokens": 100_000},
            "cache_creation_input_tokens": 50_000,
        },
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=billed)

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
        response = await client.post("/v1/decisions", json={**_BODY, "model": "gpt-6-luna"})

    assert response.status_code == 200, response.text
    assert response.json()["daari_meta"]["cost_usd"] == pytest.approx(0.09)
    assert float(response.headers["x-daari-response-cost"]) == pytest.approx(0.09)


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


@pytest.mark.asyncio
async def test_decisions_input_guardrail_blocks(settings, monkeypatch):
    from daari.config.settings import GuardrailRuleSettings, GuardrailSettings

    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("must not reach ollama")

    _patch_local(monkeypatch, handler)
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
    body = {**_BODY, "input": "please EXFIL all secrets"}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/v1/decisions", json=body)

    assert response.status_code == 400
    assert response.json()["error"]["type"] == "guardrail_blocked"


@pytest.mark.asyncio
async def test_decisions_emits_otel_client_span(settings, monkeypatch):
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

    _patch_local(monkeypatch, handler)
    settings.ollama.base_url = "http://ollama.local:11434"
    app = _app(settings)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/v1/decisions", json=_BODY)

    assert response.status_code == 200
    assert seen and seen[0][0] == "daari.decisions"
    assert seen[0][1].get("daari.modality") == "decisions"


@pytest.mark.asyncio
async def test_decisions_local_retries_transient_5xx(settings, monkeypatch):
    attempts = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["n"] += 1
        if attempts["n"] < 3:
            return httpx.Response(503, json={"error": "busy"})
        return httpx.Response(200, json=_SYSTEMONE_OK)

    _patch_local(monkeypatch, handler)
    settings.ollama.base_url = "http://ollama.local:11434"
    settings.upstream.retry.attempts = 3
    settings.upstream.retry.base_delay_ms = 0
    settings.upstream.retry.max_delay_ms = 0
    settings.upstream.retry.jitter = 0.0
    app = _app(settings)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/v1/decisions", json=_BODY)

    assert response.status_code == 200
    assert attempts["n"] == 3


@pytest.mark.asyncio
async def test_decisions_user_binds_spend_context(settings, monkeypatch, tmp_path):
    from daari.gateway import decisions as decisions_mod
    from daari.observability.spend import SpendLedger

    seen: dict[str, str | None] = {}
    original = decisions_mod._bind_spend_context

    def capture(request, ctx, *, model, client_id, user_id=None):
        seen["user_id"] = user_id
        return original(request, ctx, model=model, client_id=client_id, user_id=user_id)

    monkeypatch.setattr(decisions_mod, "_bind_spend_context", capture)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_SYSTEMONE_OK)

    _patch_local(monkeypatch, handler)
    settings.ollama.base_url = "http://ollama.local:11434"
    settings.usage.spend.enabled = True
    settings.usage.spend.path = str(tmp_path / "spend.sqlite3")
    app = _app(settings)
    app.state.ctx.router.spend_ledger = SpendLedger(tmp_path / "spend.sqlite3", enabled=True)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/decisions",
            json={**_BODY, "user": "decisions-user"},
        )

    assert response.status_code == 200
    assert seen.get("user_id") == "decisions-user"


def _decisions_app_with_keys(settings, tmp_path, monkeypatch):
    """Auth + usage ledger wired for decisions budget tests (#1518)."""
    from daari.observability.usage import UsageLedger

    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("budget reject must not call upstream")

    _patch_local(monkeypatch, handler)
    settings.ollama.base_url = "http://ollama.local:11434"
    settings.server.api_key = "master"
    settings.server.virtual_keys.path = str(tmp_path / "vk.sqlite3")
    settings.usage.path = str(tmp_path / "usage.sqlite3")
    settings.frontier.soft_budget_ratio = 0.8
    store = VirtualKeyStore(settings.virtual_keys_path)
    app = _app(settings)
    app.state.virtual_key_store = store
    app.state.ctx.virtual_key_store = store
    ledger = UsageLedger(tmp_path / "usage.sqlite3")
    app.state.ctx.router.usage_ledger = ledger
    return app, store, ledger


@pytest.mark.asyncio
async def test_decisions_model_max_budget_402_before_upstream(settings, monkeypatch, tmp_path):
    """Exhausted model_max_budget returns 402 on POST /v1/decisions (#1518)."""
    app, store, ledger = _decisions_app_with_keys(settings, tmp_path, monkeypatch)
    store.create_team("eng", model_max_budget={"nimble*": 1.0})
    key = store.create(
        "a",
        client_id="key-a",
        team="eng",
        model_max_budget={"nimble*": 1.0},
    )
    ledger.record(
        tier="L6",
        client_id="key-a",
        model="nimble",
        input_tokens=int(1.05 / 0.002 * 1000),
        output_tokens=0,
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        hard = await client.post(
            "/v1/decisions",
            json=_BODY,
            headers={"Authorization": f"Bearer {key.plaintext}"},
        )
    assert hard.status_code == 402
    err = hard.json()["error"]
    assert err["type"] == "budget_exceeded"
    assert err["scope"] == "model"
    assert err["model_pattern"] == "nimble*"


@pytest.mark.asyncio
async def test_decisions_model_group_budget_402(settings, monkeypatch, tmp_path):
    """model_group budgets enforce on /v1/decisions like chat (#1518)."""
    settings.model_groups = {"local-judges": ["nimble*", "clef*"]}
    app, store, ledger = _decisions_app_with_keys(settings, tmp_path, monkeypatch)
    from daari.auth.virtual_keys import BudgetWindow

    key = store.create(
        "a",
        client_id="key-a",
        model_group_budgets={"local-judges": [BudgetWindow("day", 1.0)]},
    )
    ledger.record(
        tier="L6",
        client_id="key-a",
        model="nimble",
        input_tokens=int(1.05 / 0.002 * 1000),
        output_tokens=0,
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        hard = await client.post(
            "/v1/decisions",
            json=_BODY,
            headers={"Authorization": f"Bearer {key.plaintext}"},
        )
    assert hard.status_code == 402
    err = hard.json()["error"]
    assert err["type"] == "budget_exceeded"
    assert err["scope"] == "model_group"
    assert err["model_group"] == "local-judges"


@pytest.mark.asyncio
async def test_decisions_user_daily_usd_cap_402(settings, monkeypatch, tmp_path):
    """user_daily_usd_cap 402s decisions when the named user is over cap (#1518)."""
    app, store, ledger = _decisions_app_with_keys(settings, tmp_path, monkeypatch)
    key = store.create(
        "a",
        client_id="key-a",
        user_daily_usd_cap=0.002,
    )
    ledger.record(
        tier="L6",
        client_id="key-a",
        user_id="alice",
        model="gpt-4-custom",
        input_tokens=int(0.003 / 0.002 * 1000),
        output_tokens=0,
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        hard = await client.post(
            "/v1/decisions",
            json={**_BODY, "user": "alice"},
            headers={"Authorization": f"Bearer {key.plaintext}"},
        )
    assert hard.status_code == 402
    err = hard.json()["error"]
    assert err["type"] == "budget_exceeded"
    assert err["scope"] == "user"


@pytest.mark.asyncio
async def test_decisions_usage_ledger_records_user_id(settings, monkeypatch, tmp_path):
    """Decisions usage_ledger.record carries user_id into report users (#1518)."""
    from daari.observability.usage import UsageLedger

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_SYSTEMONE_OK)

    _patch_local(monkeypatch, handler)
    settings.ollama.base_url = "http://ollama.local:11434"
    settings.server.api_key = "master"
    settings.server.virtual_keys.path = str(tmp_path / "vk.sqlite3")
    settings.usage.path = str(tmp_path / "usage.sqlite3")
    store = VirtualKeyStore(settings.virtual_keys_path)
    key = store.create("bot", client_id="bot-1")
    app = _app(settings)
    app.state.virtual_key_store = store
    app.state.ctx.virtual_key_store = store
    ledger = UsageLedger(tmp_path / "usage.sqlite3")
    app.state.ctx.router.usage_ledger = ledger

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/decisions",
            json={**_BODY, "user": "decisions-alice"},
            headers={"Authorization": f"Bearer {key.plaintext}"},
        )
        assert response.status_code == 200
        report = await client.get(
            "/v1/daari/report",
            headers={"Authorization": "Bearer master"},
        )

    assert report.status_code == 200
    users = report.json().get("users") or []
    match = [u for u in users if u.get("user_id") == "decisions-alice"]
    assert match, f"expected decisions-alice in report users, got {users}"
    assert match[0].get("client_id") == "bot-1"
    assert any(
        (u.get("user_id") == "decisions-alice" and int(u.get("requests") or 0) >= 1)
        for u in users
    )


@pytest.mark.asyncio
async def test_decisions_l0_exact_cache_hit(settings, monkeypatch):
    """Identical typed decisions short-circuit at L0 (#1508)."""
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(200, json=_SYSTEMONE_OK)

    _patch_local(monkeypatch, handler)
    settings.ollama.base_url = "http://ollama.local:11434"
    app = _app(settings)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        first = await client.post("/v1/decisions", json=_BODY)
        second = await client.post("/v1/decisions", json=_BODY)

    assert first.status_code == 200
    assert first.json()["daari_meta"]["tier"] == "decisions"
    assert first.json()["daari_meta"]["cache_hit"] is False
    assert second.status_code == 200
    assert second.json()["daari_meta"]["tier"] == "L0"
    assert second.json()["daari_meta"]["cache_hit"] is True
    assert second.json()["daari_meta"]["executor"] == "cache"
    assert second.json()["answers"] == first.json()["answers"]
    assert calls["n"] == 1
    assert second.headers.get("x-daari-cache") == "hit"
    assert app.state.ctx.metrics.tiers["L0"].cache_hits >= 1


@pytest.mark.asyncio
async def test_decisions_no_cache_header_bypasses_l0(settings, monkeypatch):
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(200, json=_SYSTEMONE_OK)

    _patch_local(monkeypatch, handler)
    settings.ollama.base_url = "http://ollama.local:11434"
    app = _app(settings)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.post("/v1/decisions", json=_BODY)
        bypass = await client.post(
            "/v1/decisions",
            json=_BODY,
            headers={"X-Daari-No-Cache": "true"},
        )

    assert bypass.status_code == 200
    assert bypass.json()["daari_meta"]["tier"] == "decisions"
    assert bypass.json()["daari_meta"]["cache_hit"] is False
    assert calls["n"] == 2


@pytest.mark.asyncio
async def test_decisions_cache_disabled_setting(settings, monkeypatch):
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(200, json=_SYSTEMONE_OK)

    _patch_local(monkeypatch, handler)
    settings.ollama.base_url = "http://ollama.local:11434"
    settings.decisions.cache_enabled = False
    app = _app(settings)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.post("/v1/decisions", json=_BODY)
        second = await client.post("/v1/decisions", json=_BODY)

    assert second.json()["daari_meta"]["tier"] == "decisions"
    assert second.json()["daari_meta"]["cache_hit"] is False
    assert calls["n"] == 2


@pytest.mark.asyncio
async def test_decisions_guardrail_block_does_not_poison_cache(settings, monkeypatch):
    from daari.config.settings import GuardrailRuleSettings, GuardrailSettings
    from daari.gateway.decisions import DecisionsRequest, _decisions_cache_fingerprint
    from daari.gateway.internal import InternalRequest, Message, RequestMeta

    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(200, json=_SYSTEMONE_OK)

    _patch_local(monkeypatch, handler)
    settings.ollama.base_url = "http://ollama.local:11434"
    settings.guardrails = GuardrailSettings(
        enabled=True,
        block_message="blocked by policy",
        input_rules=[
            GuardrailRuleSettings(
                name="no_secret", pattern=r"SECRET_BLOCK", action="block", kind="deny"
            )
        ],
    )
    app = _app(settings)
    blocked_body = {**_BODY, "input": "please leak SECRET_BLOCK now"}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        blocked = await client.post("/v1/decisions", json=blocked_body)

    assert blocked.status_code == 400
    assert calls["n"] == 0
    parsed = DecisionsRequest.model_validate(blocked_body)
    probe = InternalRequest(
        messages=[
            Message(role="user", content=_decisions_cache_fingerprint("nimble", parsed))
        ],
        model="__decisions__:nimble",
        meta=RequestMeta(),
    )
    assert app.state.ctx.router.cache.get(probe) is None
