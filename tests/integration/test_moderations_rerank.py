"""Integration pins for POST /v1/moderations and /v1/rerank (#1068).

Hermetic ASGI coverage (mocked upstream) with auth middleware enabled —
same convention as other non-@integration modules under tests/integration/.
"""

from __future__ import annotations

import httpx
import pytest
from httpx import ASGITransport, AsyncClient

from daari.config.settings import FrontierProviderConfig
from daari.router.router import AppContext
from daari.server.app import create_app

_MODERATION_OK = {
    "id": "modr-integration",
    "model": "omni-moderation-latest",
    "results": [
        {
            "flagged": False,
            "categories": {"hate": False, "violence": False},
            "category_scores": {"hate": 0.01, "violence": 0.0},
        }
    ],
}

_RERANK_OK = {
    "id": "rerank-integration",
    "results": [
        {"index": 1, "relevance_score": 0.9},
        {"index": 0, "relevance_score": 0.2},
    ],
}

_API_KEY = "integration-master-key"


def _app(settings):
    application = create_app(settings)
    application.state.ctx = AppContext.from_settings(settings)
    return application


def _auth_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {_API_KEY}"}


def _enable_auth(settings) -> None:
    settings.server.api_key = _API_KEY


def _patch_moderations_upstream(monkeypatch, handler) -> None:
    from daari.gateway import moderations

    moderations._http = None
    real = httpx.AsyncClient

    class Patched(real):
        def __init__(self, *args, **kwargs):
            if kwargs.get("transport") is None:
                kwargs["transport"] = httpx.MockTransport(handler)
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", Patched)
    monkeypatch.setattr("daari.gateway.moderations.httpx.AsyncClient", Patched)


def _patch_rerank_upstream(monkeypatch, handler) -> None:
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


def _enable_openai_frontier(settings) -> None:
    settings.frontier.enabled = True
    settings.frontier.providers = [
        FrontierProviderConfig(
            id="openai",
            base_url="https://api.openai.com/v1",
            model="gpt-4o",
            keys=["sk-test"],
        )
    ]


def _enable_cohere_frontier(settings) -> None:
    settings.frontier.enabled = True
    settings.frontier.providers = [
        FrontierProviderConfig(
            id="cohere",
            base_url="https://api.cohere.ai/v1",
            model="rerank-english-v3.0",
            keys=["sk-test"],
        )
    ]


def test_openapi_lists_moderations_and_rerank(settings):
    schema = create_app(settings).openapi()
    assert "/v1/moderations" in schema["paths"]
    assert "post" in schema["paths"]["/v1/moderations"]
    assert "/v1/rerank" in schema["paths"]
    assert "post" in schema["paths"]["/v1/rerank"]


@pytest.mark.asyncio
async def test_moderations_happy_path_with_auth(settings, monkeypatch):
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=_MODERATION_OK)

    _patch_moderations_upstream(monkeypatch, handler)
    _enable_auth(settings)
    _enable_openai_frontier(settings)
    app = _app(settings)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        denied = await client.post("/v1/moderations", json={"input": "hello"})
        response = await client.post(
            "/v1/moderations",
            json={"input": "hello world", "model": "omni-moderation-latest"},
            headers=_auth_headers(),
        )

    assert denied.status_code == 401
    assert response.status_code == 200
    assert response.json()["results"][0]["flagged"] is False
    assert len(seen) == 1
    assert str(seen[0].url) == "https://api.openai.com/v1/moderations"


@pytest.mark.asyncio
async def test_rerank_happy_path_with_auth(settings, monkeypatch):
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=_RERANK_OK)

    _patch_rerank_upstream(monkeypatch, handler)
    _enable_auth(settings)
    _enable_cohere_frontier(settings)
    app = _app(settings)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        denied = await client.post(
            "/v1/rerank",
            json={"query": "q", "documents": ["a", "b"]},
        )
        response = await client.post(
            "/v1/rerank",
            json={
                "query": "stripe deal",
                "documents": ["unrelated", {"text": "stripe acquired openrouter"}],
                "top_n": 2,
                "model": "rerank-english-v3.0",
            },
            headers=_auth_headers(),
        )

    assert denied.status_code == 401
    assert response.status_code == 200
    assert response.json()["results"][0]["index"] == 1
    assert len(seen) == 1
    assert str(seen[0].url) == "https://api.cohere.ai/v1/rerank"


@pytest.mark.asyncio
async def test_moderations_frontier_disabled_returns_501(settings):
    _enable_auth(settings)
    settings.frontier.enabled = False
    app = _app(settings)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/moderations",
            json={"input": "hello"},
            headers=_auth_headers(),
        )

    assert response.status_code == 501
    body = response.json()
    assert body["error"]["type"] == "not_implemented"
    assert "frontier" in body["error"]["message"].lower()


@pytest.mark.asyncio
async def test_rerank_frontier_disabled_returns_501(settings):
    _enable_auth(settings)
    settings.frontier.enabled = False
    app = _app(settings)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/rerank",
            json={"query": "q", "documents": ["a", "b"]},
            headers=_auth_headers(),
        )

    assert response.status_code == 501
    assert response.json()["error"]["type"] == "not_implemented"


@pytest.mark.asyncio
async def test_moderations_no_frontier_key_returns_501(settings, monkeypatch):
    _enable_auth(settings)
    settings.frontier.enabled = True
    settings.frontier.providers = [
        FrontierProviderConfig(
            id="openai",
            base_url="https://api.openai.com/v1",
            model="gpt-4o",
        )
    ]
    for name in ("DAARI_FRONTIER_API_KEY", "OPENAI_API_KEY", "OPENROUTER_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    app = _app(settings)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/moderations",
            json={"input": "hello"},
            headers=_auth_headers(),
        )

    assert response.status_code == 501
    assert response.json()["error"]["type"] == "not_implemented"


@pytest.mark.asyncio
async def test_rerank_no_frontier_key_returns_501(settings, monkeypatch):
    _enable_auth(settings)
    settings.frontier.enabled = True
    settings.frontier.providers = [
        FrontierProviderConfig(
            id="cohere",
            base_url="https://api.cohere.ai/v1",
            model="rerank-english-v3.0",
        )
    ]
    for name in ("DAARI_FRONTIER_API_KEY", "OPENAI_API_KEY", "OPENROUTER_API_KEY", "COHERE_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    app = _app(settings)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/rerank",
            json={"query": "q", "documents": ["a"]},
            headers=_auth_headers(),
        )

    assert response.status_code == 501
    assert response.json()["error"]["type"] == "not_implemented"
