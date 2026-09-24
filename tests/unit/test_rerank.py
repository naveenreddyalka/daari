"""POST /v1/rerank L6 passthrough (#1051)."""

from __future__ import annotations

import httpx
import pytest
from httpx import ASGITransport, AsyncClient

from daari.config.settings import FrontierProviderConfig
from daari.gateway.rerank import normalize_documents, resolve_rerank_target
from daari.router.router import AppContext
from daari.server.app import create_app


def _patch_upstream(monkeypatch, handler):
    from daari.gateway import rerank

    rerank._http = None
    real = httpx.AsyncClient

    class Patched(real):
        def __init__(self, *args, **kwargs):
            if kwargs.get("transport") is None:
                kwargs["transport"] = httpx.MockTransport(handler)
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", Patched)
    monkeypatch.setattr("daari.gateway.rerank.httpx.AsyncClient", Patched)


def _app(settings):
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    return app


_RERANK_OK = {
    "id": "rerank-test",
    "results": [
        {"index": 1, "relevance_score": 0.9},
        {"index": 0, "relevance_score": 0.2},
    ],
}


def test_openapi_lists_rerank(settings):
    schema = create_app(settings).openapi()
    assert "/v1/rerank" in schema["paths"]
    assert "post" in schema["paths"]["/v1/rerank"]


def test_normalize_documents_accepts_strings_and_text_objects():
    assert normalize_documents(["a", {"text": "b"}]) == ["a", "b"]


def test_normalize_documents_rejects_bad_shape():
    with pytest.raises(ValueError):
        normalize_documents([{"body": "nope"}])  # type: ignore[list-item]


def test_resolve_target_none_when_frontier_disabled(settings):
    settings.frontier.enabled = False
    assert resolve_rerank_target(settings) is None


@pytest.mark.asyncio
async def test_disabled_frontier_returns_501(settings):
    settings.frontier.enabled = False
    app = _app(settings)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/rerank",
            json={"query": "q", "documents": ["a", "b"]},
        )

    assert response.status_code == 501
    assert response.json()["error"]["type"] == "not_implemented"


@pytest.mark.asyncio
async def test_forwards_to_frontier_and_returns_results(settings, monkeypatch):
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=_RERANK_OK)

    _patch_upstream(monkeypatch, handler)
    settings.frontier.enabled = True
    settings.frontier.providers = [
        FrontierProviderConfig(
            id="cohere",
            base_url="https://api.cohere.ai/v1",
            model="rerank-english-v3.0",
            keys=["sk-test"],
        )
    ]
    app = _app(settings)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/rerank",
            json={
                "query": "stripe deal",
                "documents": ["unrelated", {"text": "stripe acquired openrouter"}],
                "top_n": 2,
                "model": "rerank-english-v3.0",
            },
        )

    assert response.status_code == 200
    assert response.json()["results"][0]["index"] == 1
    assert len(seen) == 1
    req = seen[0]
    assert str(req.url) == "https://api.cohere.ai/v1/rerank"
    assert req.headers["authorization"] == "Bearer sk-test"
    payload = req.read()
    assert b"stripe deal" in payload
    assert b"top_n" in payload
    assert b"stripe acquired openrouter" in payload


@pytest.mark.asyncio
async def test_upstream_http_error_propagates(settings, monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            400,
            json={"error": {"type": "invalid_request", "message": "bad docs"}},
        )

    _patch_upstream(monkeypatch, handler)
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
            "/v1/rerank",
            json={"query": "q", "documents": ["a"]},
        )

    assert response.status_code == 400
    assert response.json()["error"]["type"] == "invalid_request"
