"""POST /v1/ocr — local multimodal / L6 passthrough (#1263)."""

from __future__ import annotations

import httpx
import pytest
from httpx import ASGITransport, AsyncClient

from daari.auth.rate_families import rate_limit_family
from daari.auth.virtual_keys import VirtualKeyStore
from daari.config.settings import FrontierProviderConfig
from daari.gateway.ocr import resolve_ocr_target
from daari.router.router import AppContext
from daari.server.app import create_app

_OCR_OK = {
    "object": "ocr",
    "model": "mistral-ocr-latest",
    "pages": [
        {
            "index": 0,
            "markdown": "Hello from OCR",
            "dimensions": {"dpi": 200, "height": 100, "width": 100},
            "images": [],
        }
    ],
    "usage_info": {"pages_processed": 1, "doc_size_bytes": 42},
    "document_annotation": None,
}

_DOC = {
    "type": "image_url",
    "image_url": "data:image/png;base64,iVBORw0KGgo=",
}


def _patch_upstream(monkeypatch, handler):
    from daari.gateway import ocr

    ocr._http = None
    real = httpx.AsyncClient

    class Patched(real):
        def __init__(self, *args, **kwargs):
            if kwargs.get("transport") is None:
                kwargs["transport"] = httpx.MockTransport(handler)
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", Patched)
    monkeypatch.setattr("daari.gateway.ocr.httpx.AsyncClient", Patched)


def _app(settings):
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    return app


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


def test_openapi_lists_ocr(settings):
    schema = create_app(settings).openapi()
    assert "/v1/ocr" in schema["paths"]
    assert "post" in schema["paths"]["/v1/ocr"]


def test_rate_limit_family_maps_ocr():
    assert rate_limit_family("/v1/ocr") == "ocr"


def test_resolve_target_none_when_unconfigured(settings, monkeypatch):
    settings.ocr.base_url = ""
    settings.ocr.vision_model = ""
    settings.frontier.enabled = False
    for name in ("DAARI_FRONTIER_API_KEY", "OPENAI_API_KEY", "OPENROUTER_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    assert resolve_ocr_target(settings) is None


def test_resolve_prefers_local_base_url(settings):
    settings.ocr.base_url = "http://ocr.local/v1"
    settings.ocr.model = "local-ocr"
    settings.frontier.enabled = False
    target = resolve_ocr_target(settings)
    assert target is not None
    assert target.via == "local"
    assert target.base_url == "http://ocr.local/v1"
    assert target.default_model == "local-ocr"


def test_resolve_prefers_vision_model(settings):
    settings.ocr.base_url = ""
    settings.ocr.vision_model = "llava:latest"
    settings.ollama.base_url = "http://127.0.0.1:11434"
    settings.frontier.enabled = False
    target = resolve_ocr_target(settings)
    assert target is not None
    assert target.via == "vision"
    assert target.default_model == "llava:latest"


@pytest.mark.asyncio
async def test_unconfigured_returns_503(settings):
    settings.ocr.base_url = ""
    settings.ocr.vision_model = ""
    settings.frontier.enabled = False
    app = _app(settings)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/ocr",
            json={"model": "mistral-ocr-latest", "document": _DOC},
        )

    assert response.status_code == 503
    body = response.json()
    assert body["error"]["type"] in {"service_unavailable", "not_implemented", "unavailable"}
    assert "ocr" in body["error"]["message"].lower() or "frontier" in body["error"]["message"].lower()


@pytest.mark.asyncio
async def test_missing_document_returns_400(settings):
    _enable_frontier(settings)
    app = _app(settings)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/v1/ocr", json={"model": "mistral-ocr-latest"})

    assert response.status_code == 400
    assert response.json()["error"]["type"] == "invalid_request_error"


@pytest.mark.asyncio
async def test_forwards_to_frontier_and_returns_pages(settings, monkeypatch):
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=_OCR_OK)

    _patch_upstream(monkeypatch, handler)
    _enable_frontier(settings)
    settings.ocr.base_url = ""
    settings.ocr.vision_model = ""
    app = _app(settings)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/ocr",
            json={"model": "mistral-ocr-latest", "document": _DOC},
        )

    assert response.status_code == 200
    assert response.json()["pages"][0]["markdown"] == "Hello from OCR"
    assert len(seen) == 1
    req = seen[0]
    assert str(req.url) == "https://api.openai.com/v1/ocr"
    assert req.headers["authorization"] == "Bearer sk-test"
    payload = req.read()
    assert b"mistral-ocr-latest" in payload
    assert b"image_url" in payload


@pytest.mark.asyncio
async def test_local_base_url_passthrough(settings, monkeypatch):
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=_OCR_OK)

    _patch_upstream(monkeypatch, handler)
    settings.frontier.enabled = False
    settings.ocr.base_url = "http://ocr.local/v1"
    settings.ocr.model = "local-ocr"
    app = _app(settings)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/ocr",
            json={"document": _DOC},
        )

    assert response.status_code == 200
    assert len(seen) == 1
    assert str(seen[0].url) == "http://ocr.local/v1/ocr"
    assert b"local-ocr" in seen[0].read()


@pytest.mark.asyncio
async def test_local_vision_wraps_ollama_chat(settings, monkeypatch):
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            200,
            json={"message": {"role": "assistant", "content": "Receipt total $15"}},
        )

    _patch_upstream(monkeypatch, handler)
    settings.frontier.enabled = False
    settings.ocr.base_url = ""
    settings.ocr.vision_model = "llava:latest"
    settings.ollama.base_url = "http://ollama.local"
    app = _app(settings)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/ocr",
            json={"document": _DOC},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["object"] == "ocr"
    assert body["pages"][0]["markdown"] == "Receipt total $15"
    assert body["model"] == "llava:latest"
    assert len(seen) == 1
    assert "/api/chat" in str(seen[0].url)


@pytest.mark.asyncio
async def test_upstream_http_error_propagates(settings, monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            429,
            json={"error": {"type": "rate_limit", "message": "slow down"}},
        )

    _patch_upstream(monkeypatch, handler)
    _enable_frontier(settings)
    app = _app(settings)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/ocr",
            json={"model": "mistral-ocr-latest", "document": _DOC},
        )

    assert response.status_code == 429
    assert response.json()["error"]["type"] == "rate_limit"


def _enable_spend(settings, tmp_path):
    settings.usage.spend.enabled = True
    settings.usage.spend.path = str(tmp_path / "spend.sqlite3")


def _spend_rows(app):
    ledger = app.state.ctx.router.spend_ledger
    return list(ledger.iter_rows(since="2000-01-01T00:00:00+00:00"))


@pytest.mark.asyncio
async def test_virtual_key_spend_metered(settings, tmp_path, monkeypatch):
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=_OCR_OK)

    _patch_upstream(monkeypatch, handler)
    _enable_frontier(settings)
    _enable_spend(settings, tmp_path)
    settings.server.api_key = "master"
    settings.server.virtual_keys.path = str(tmp_path / "vk.sqlite3")
    store = VirtualKeyStore(settings.virtual_keys_path)
    key = store.create("ocr-bot", client_id="client-ocr", team="eng")
    app = _app(settings)
    app.state.virtual_key_store = store
    app.state.ctx.virtual_key_store = store

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/ocr",
            json={"model": "mistral-ocr-latest", "document": _DOC, "user": "alice"},
            headers={"Authorization": f"Bearer {key.plaintext}"},
        )

    assert response.status_code == 200, response.text
    assert len(seen) == 1
    rows = _spend_rows(app)
    assert len(rows) == 1
    assert rows[0]["tier"] == "L6"
    assert rows[0]["key_id"] == key.key.key_id
    assert rows[0]["team_id"] == key.key.team_id
    assert rows[0]["model"] == "mistral-ocr-latest"


def test_ocr_metrics_record_modality_ocr_not_chat():
    """Prometheus must label OCR as modality=ocr, not collapse to chat (#1445)."""
    from daari.gateway import ocr
    from daari.observability.metrics import Metrics, infer_modality
    from daari.observability.prometheus import render_prometheus

    assert infer_modality("ocr", modality="ocr") == "ocr"

    class Ctx:
        def __init__(self):
            self.metrics = Metrics()
            self.router = type("R", (), {"usage_ledger": None})()

    ctx = Ctx()
    ocr._record_request(
        ctx, client_id="c", model="mistral-ocr-latest", prompt_chars=40, completion_chars=80
    )
    text = render_prometheus(ctx.metrics)
    assert 'daari_requests_total{tier="ocr",modality="ocr"} 1' in text
    assert 'daari_requests_total{tier="ocr",modality="chat"}' not in text
    assert 'daari_tokens_total{modality="ocr",tier="ocr",direction="input"}' in text


@pytest.mark.asyncio
async def test_ocr_output_guardrail_redacts(settings, monkeypatch):
    from daari.config.settings import GuardrailRuleSettings, GuardrailSettings

    secret_body = {
        **_OCR_OK,
        "pages": [
            {
                "index": 0,
                "markdown": "SSN is SECRET-VALUE on file",
                "dimensions": {"dpi": 200, "height": 100, "width": 100},
                "images": [],
            }
        ],
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=secret_body)

    _patch_upstream(monkeypatch, handler)
    settings.ocr.base_url = "http://ocr.local/v1"
    settings.ocr.model = "local-ocr"
    settings.frontier.enabled = False
    settings.guardrails = GuardrailSettings(
        enabled=True,
        output_rules=[
            GuardrailRuleSettings(
                name="scrub_out", pattern=r"SECRET-VALUE", action="redact", kind="deny"
            )
        ],
    )
    app = _app(settings)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/v1/ocr", json={"document": _DOC})

    assert response.status_code == 200, response.text
    markdown = response.json()["pages"][0]["markdown"]
    assert "SECRET-VALUE" not in markdown
    assert "<redacted>" in markdown


@pytest.mark.asyncio
async def test_ocr_output_guardrail_blocks(settings, monkeypatch):
    from daari.config.settings import GuardrailRuleSettings, GuardrailSettings

    secret_body = {
        **_OCR_OK,
        "pages": [
            {
                "index": 0,
                "markdown": "classified CONFIDENTIAL leak",
                "dimensions": {"dpi": 200, "height": 100, "width": 100},
                "images": [],
            }
        ],
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=secret_body)

    _patch_upstream(monkeypatch, handler)
    settings.ocr.base_url = "http://ocr.local/v1"
    settings.ocr.model = "local-ocr"
    settings.frontier.enabled = False
    settings.guardrails = GuardrailSettings(
        enabled=True,
        block_message="blocked by policy",
        output_rules=[
            GuardrailRuleSettings(
                name="no_conf", pattern=r"CONFIDENTIAL", action="block", kind="deny"
            )
        ],
    )
    app = _app(settings)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/v1/ocr", json={"document": _DOC})

    assert response.status_code == 400
    assert response.json()["error"]["type"] == "guardrail_blocked"


@pytest.mark.asyncio
async def test_ocr_upstream_emits_otel_client_span(settings, monkeypatch):
    """OCR wraps the upstream hop in modality_client_span (no global provider override)."""
    from contextlib import contextmanager

    from daari.observability import otel as otel_mod

    seen: list[tuple[str, dict]] = []

    @contextmanager
    def fake_span(name, *, attributes=None):
        seen.append((name, dict(attributes or {})))
        yield object()

    monkeypatch.setattr(otel_mod, "modality_client_span", fake_span)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_OCR_OK)

    _patch_upstream(monkeypatch, handler)
    settings.ocr.base_url = "http://ocr.local/v1"
    settings.ocr.model = "local-ocr"
    settings.frontier.enabled = False
    app = _app(settings)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/v1/ocr", json={"document": _DOC})

    assert response.status_code == 200, response.text
    assert seen, "expected daari.ocr client span"
    name, attrs = seen[0]
    assert name == "daari.ocr"
    assert attrs.get("daari.modality") == "ocr"
    assert attrs.get("gen_ai.operation.name") == "ocr"


@pytest.mark.asyncio
async def test_ocr_input_guardrail_blocks(settings, monkeypatch):
    """Document source text is screened before upstream dispatch (#1476)."""
    from daari.config.settings import GuardrailRuleSettings, GuardrailSettings

    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("must not call OCR upstream when input blocked")

    _patch_upstream(monkeypatch, handler)
    settings.ocr.base_url = "http://ocr.local/v1"
    settings.ocr.model = "local-ocr"
    settings.frontier.enabled = False
    settings.guardrails = GuardrailSettings(
        enabled=True,
        block_message="blocked by policy",
        input_rules=[
            GuardrailRuleSettings(
                name="no_evil", pattern=r"evil\.example", action="block", kind="deny"
            )
        ],
    )
    app = _app(settings)
    doc = {"type": "image_url", "image_url": "https://evil.example/doc.png"}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/v1/ocr", json={"document": doc})

    assert response.status_code == 400
    assert response.json()["error"]["type"] == "guardrail_blocked"


def test_ocr_catalog_ships_per_page_rate(settings):
    """mistral-ocr-latest usd_per_page is operator-overridable (#2282)."""
    from daari.config.settings import ModelPrice
    from daari.gateway.ocr import ocr_usd_per_page
    from daari.pricing import resolve_price

    price = resolve_price("mistral-ocr-latest", settings.pricing, fallback_per_1k=0.002)
    assert price.is_fallback is False
    assert ocr_usd_per_page("mistral-ocr-latest", settings.pricing) == pytest.approx(0.001)

    settings.pricing.models["mistral-ocr-latest"] = ModelPrice(
        input_per_1m=0.0,
        output_per_1m=0.0,
        usd_per_page=0.005,
    )
    assert ocr_usd_per_page("mistral-ocr-latest", settings.pricing) == pytest.approx(0.005)


def test_price_ocr_uses_pages_processed():
    from daari.config.settings import PricingSettings
    from daari.gateway.ocr import price_ocr

    pricing = PricingSettings()
    charge = price_ocr(
        "mistral-ocr-latest",
        {
            "pages": [{"index": 0, "markdown": "a"}, {"index": 1, "markdown": "b"}],
            "usage_info": {"pages_processed": 3, "doc_size_bytes": 10},
        },
        pricing=pricing,
    )
    assert charge.pages == 3
    assert charge.cost_usd == pytest.approx(0.003)


def test_price_ocr_falls_back_to_pages_array_length():
    from daari.config.settings import PricingSettings
    from daari.gateway.ocr import price_ocr

    pricing = PricingSettings()
    charge = price_ocr(
        "mistral-ocr-latest",
        {"pages": [{"index": 0, "markdown": "a"}, {"index": 1, "markdown": "b"}]},
        pricing=pricing,
    )
    assert charge.pages == 2
    assert charge.cost_usd == pytest.approx(0.002)


def test_price_ocr_operator_override_wins():
    from daari.config.settings import ModelPrice, PricingSettings
    from daari.gateway.ocr import price_ocr

    pricing = PricingSettings()
    pricing.models["mistral-ocr-latest"] = ModelPrice(
        input_per_1m=0.0,
        output_per_1m=0.0,
        usd_per_page=0.01,
    )
    charge = price_ocr(
        "mistral-ocr-latest",
        {"usage_info": {"pages_processed": 2}},
        pricing=pricing,
    )
    assert charge.cost_usd == pytest.approx(0.02)


@pytest.mark.asyncio
async def test_frontier_ocr_bills_pages_local_stays_zero(settings, tmp_path, monkeypatch):
    """Frontier OCR meters pages × rate; local OCR stays $0 (#2282)."""
    from daari.gateway.cost_headers import COST_HEADER

    body = {
        **_OCR_OK,
        "usage_info": {"pages_processed": 5, "doc_size_bytes": 42},
    }

    def frontier_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=body)

    _patch_upstream(monkeypatch, frontier_handler)
    _enable_frontier(settings)
    _enable_spend(settings, tmp_path)
    settings.ocr.base_url = ""
    settings.ocr.vision_model = ""
    app = _app(settings)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        frontier = await client.post(
            "/v1/ocr",
            json={"model": "mistral-ocr-latest", "document": _DOC},
        )
    assert frontier.status_code == 200, frontier.text
    expected = 5 * 0.001
    assert float(frontier.headers[COST_HEADER]) == pytest.approx(expected)
    rows = [r for r in _spend_rows(app) if r["tier"] == "L6"]
    assert len(rows) == 1
    assert float(rows[0]["cost_usd"]) == pytest.approx(expected)
    assert rows[0]["model"] == "mistral-ocr-latest"

    def local_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=body)

    _patch_upstream(monkeypatch, local_handler)
    settings.ocr.base_url = "http://ocr.local/v1"
    settings.ocr.model = "local-ocr"
    settings.frontier.enabled = False
    local_app = _app(settings)
    async with AsyncClient(
        transport=ASGITransport(app=local_app), base_url="http://test"
    ) as client:
        local = await client.post(
            "/v1/ocr",
            json={"model": "local-ocr", "document": _DOC},
        )
    assert local.status_code == 200, local.text
    assert float(local.headers[COST_HEADER]) == 0.0
    local_rows = [r for r in _spend_rows(local_app) if r["tier"] == "ocr"]
    assert len(local_rows) == 1
    assert float(local_rows[0]["cost_usd"]) == 0.0


@pytest.mark.asyncio
async def test_frontier_ocr_spend_hits_daily_budget(settings, tmp_path, monkeypatch):
    """Budget-capped key that exhausts via frontier OCR gets 402 (#2282)."""

    body = {
        **_OCR_OK,
        "usage_info": {"pages_processed": 2000, "doc_size_bytes": 42},
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=body)

    _patch_upstream(monkeypatch, handler)
    _enable_frontier(settings)
    _enable_spend(settings, tmp_path)
    settings.ocr.base_url = ""
    settings.ocr.vision_model = ""
    settings.server.api_key = "master"
    settings.server.virtual_keys.path = str(tmp_path / "vk.sqlite3")
    store = VirtualKeyStore(settings.virtual_keys_path)
    # 2000 pages × $0.001 = $2.00; daily cap $1.
    key = store.create("bot", client_id="client-bot", daily_budget_usd=1.0)
    app = _app(settings)
    app.state.virtual_key_store = store
    app.state.ctx.virtual_key_store = store
    headers = {"Authorization": f"Bearer {key.plaintext}"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        first = await client.post(
            "/v1/ocr",
            json={"model": "mistral-ocr-latest", "document": _DOC},
            headers=headers,
        )
        second = await client.post(
            "/v1/ocr",
            json={"model": "mistral-ocr-latest", "document": _DOC},
            headers=headers,
        )
    assert first.status_code == 200, first.text
    assert second.status_code == 402
    assert second.json()["error"]["type"] == "budget_exceeded"
