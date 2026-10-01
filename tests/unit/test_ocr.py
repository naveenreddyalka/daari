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
    assert rows[0]["tier"] == "ocr"
    assert rows[0]["key_id"] == key.key.key_id
    assert rows[0]["team_id"] == key.key.team_id
    assert rows[0]["model"] == "mistral-ocr-latest"
