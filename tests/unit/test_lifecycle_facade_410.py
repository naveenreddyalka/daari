"""Retired-model 410 on every inference facade (#1676)."""

from __future__ import annotations

import httpx
import pytest
from httpx import ASGITransport, AsyncClient

from daari.config.settings import Settings
from daari.gateway.internal import DaariMeta, InternalRequest, InternalResponse
from daari.router.router import AppContext
from daari.server.app import create_app


def _settings_with_lifecycle(**overrides: object) -> Settings:
    models: dict[str, object] = {
        "lifecycle": {
            "llama3.2:3b": {
                "lifecycle": "deprecated",
                "deprecated_at": "2026-01-01T00:00:00Z",
                "retires_at": "2026-12-01T00:00:00Z",
            },
            "retired-model": {"lifecycle": "retired"},
        },
        "reject_retired": True,
        "l3": "llama3.2:3b",
    }
    models.update(overrides)
    return Settings.model_validate(
        {
            "models": models,
            "frontier": {
                "enabled": True,
                "providers": [
                    {"id": "openai", "model": "gpt-6-luna", "api_key": "sk-test"},
                ],
            },
            "ocr": {"base_url": "http://ocr.local", "model": "mistral-ocr-latest"},
        }
    )


def _app(configured: Settings):
    app = create_app(configured)
    app.state.ctx = AppContext.from_settings(configured)
    return app


def _assert_retired_410(response) -> None:
    assert response.status_code == 410
    err = response.json()["error"]
    assert err["type"] == "model_retired"
    assert err["code"] == "model_retired"


@pytest.mark.asyncio
async def test_ollama_chat_rejects_retired_model(monkeypatch):
    configured = _settings_with_lifecycle()
    app = _app(configured)
    routed = False

    async def fake_route(request: InternalRequest) -> InternalResponse:
        nonlocal routed
        routed = True
        return InternalResponse(
            content="should not run",
            model=request.model,
            daari_meta=DaariMeta(tier="L3", executor="ollama", provider_id="ollama"),
        )

    monkeypatch.setattr(app.state.ctx.router, "route", fake_route)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/api/chat",
            json={
                "model": "retired-model",
                "messages": [{"role": "user", "content": "hi"}],
                "stream": False,
            },
        )
    _assert_retired_410(response)
    assert routed is False


@pytest.mark.asyncio
async def test_ollama_generate_rejects_retired_model(monkeypatch):
    configured = _settings_with_lifecycle()
    app = _app(configured)
    routed = False

    async def fake_route(request: InternalRequest) -> InternalResponse:
        nonlocal routed
        routed = True
        return InternalResponse(
            content="should not run",
            model=request.model,
            daari_meta=DaariMeta(tier="L3", executor="ollama", provider_id="ollama"),
        )

    monkeypatch.setattr(app.state.ctx.router, "route", fake_route)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/api/generate",
            json={"model": "retired-model", "prompt": "hi", "stream": False},
        )
    _assert_retired_410(response)
    assert routed is False


@pytest.mark.asyncio
async def test_ollama_chat_allows_deprecated_with_warning(monkeypatch):
    configured = _settings_with_lifecycle()
    app = _app(configured)

    async def fake_route(request: InternalRequest) -> InternalResponse:
        return InternalResponse(
            content="ok",
            model=request.model,
            daari_meta=DaariMeta(
                tier="L3",
                executor="ollama",
                provider_id="ollama",
                warning="model_deprecated",
            ),
        )

    monkeypatch.setattr(app.state.ctx.router, "route", fake_route)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/api/chat",
            json={
                "model": "llama3.2:3b",
                "messages": [{"role": "user", "content": "hi"}],
                "stream": False,
            },
        )
    assert response.status_code == 200
    assert response.json()["daari_meta"]["warning"] == "model_deprecated"


@pytest.mark.asyncio
async def test_decisions_rejects_retired_model(monkeypatch):
    configured = _settings_with_lifecycle()
    app = _app(configured)
    called = False

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal called
        called = True
        return httpx.Response(200, json={"answers": {}})

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

    body = {
        "model": "retired-model",
        "input": "I was charged twice.",
        "questions": [
            {
                "type": "choice",
                "name": "department",
                "instructions": "Which department?",
                "choices": [
                    {"value": "billing", "description": "Payments"},
                    {"value": "other", "description": "Else"},
                ],
            }
        ],
    }
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post("/v1/decisions", json=body)
    _assert_retired_410(response)
    assert called is False


@pytest.mark.asyncio
async def test_embeddings_rejects_retired_model(monkeypatch):
    configured = _settings_with_lifecycle()
    app = _app(configured)
    called = {"n": 0}

    class BoomEmbedder:
        async def embed(self, text: str, *, model: str | None = None) -> list[float] | None:
            called["n"] += 1
            raise AssertionError("embedder should not run")

        async def embed_many(
            self, texts: list[str], *, model: str | None = None
        ) -> list[list[float] | None]:
            called["n"] += 1
            raise AssertionError("embedder should not run")

    app.state.ctx.router.semantic_cache.embedder = BoomEmbedder()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/v1/embeddings",
            json={"model": "retired-model", "input": "hello"},
        )
    _assert_retired_410(response)
    assert called["n"] == 0


@pytest.mark.asyncio
async def test_ocr_rejects_retired_model(monkeypatch):
    configured = _settings_with_lifecycle()
    app = _app(configured)
    called = False

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal called
        called = True
        return httpx.Response(200, json={"pages": [{"markdown": "x"}]})

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

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/v1/ocr",
            json={
                "model": "retired-model",
                "document": {
                    "type": "image_url",
                    "image_url": "data:image/png;base64,AAAA",
                },
            },
        )
    _assert_retired_410(response)
    assert called is False


@pytest.mark.asyncio
async def test_systemone_rejects_retired_model(monkeypatch):
    configured = _settings_with_lifecycle()
    app = _app(configured)
    called = False

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal called
        called = True
        return httpx.Response(200, json={"answers": {}})

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

    body = {
        "model": "retired-model",
        "state": "Our checkout has returned 500 errors.",
        "questions": {
            "label": {
                "type": "choice",
                "instructions": "Which label?",
                "criteria": {"bug": "Software errors", "billing": "Payments"},
            }
        },
    }
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post("/v1/systemone", json=body)
    _assert_retired_410(response)
    assert called is False


@pytest.mark.asyncio
async def test_shipped_default_retired_rejected_on_embeddings():
    """Shipped calendar retired ids (chatgpt-4o-latest) 410 without operator map."""
    configured = Settings.model_validate({"models": {"reject_retired": True}})
    app = _app(configured)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/v1/embeddings",
            json={"model": "chatgpt-4o-latest", "input": "hello"},
        )
    _assert_retired_410(response)


@pytest.mark.asyncio
async def test_reject_retired_false_allows_facades(monkeypatch):
    configured = _settings_with_lifecycle(reject_retired=False)
    app = _app(configured)

    async def fake_route(request: InternalRequest) -> InternalResponse:
        return InternalResponse(
            content="ok",
            model=request.model,
            daari_meta=DaariMeta(tier="L3", executor="ollama", provider_id="ollama"),
        )

    monkeypatch.setattr(app.state.ctx.router, "route", fake_route)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/api/chat",
            json={
                "model": "retired-model",
                "messages": [{"role": "user", "content": "hi"}],
                "stream": False,
            },
        )
    assert response.status_code == 200
