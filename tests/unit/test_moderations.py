"""POST /v1/moderations L6 passthrough (#1050)."""

from __future__ import annotations

import httpx
import pytest
from httpx import ASGITransport, AsyncClient

from daari.config.settings import FrontierProviderConfig
from daari.gateway.moderations import resolve_moderations_target
from daari.router.router import AppContext
from daari.server.app import create_app


def _patch_upstream(monkeypatch, handler):
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


def _app(settings):
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    return app


_MODERATION_OK = {
    "id": "modr-test",
    "model": "omni-moderation-latest",
    "results": [
        {
            "flagged": False,
            "categories": {"hate": False, "violence": False},
            "category_scores": {"hate": 0.01, "violence": 0.0},
        }
    ],
}


def test_openapi_lists_moderations(settings):
    schema = create_app(settings).openapi()
    assert "/v1/moderations" in schema["paths"]
    assert "post" in schema["paths"]["/v1/moderations"]


def test_resolve_target_none_when_frontier_disabled(settings):
    settings.frontier.enabled = False
    assert resolve_moderations_target(settings) is None


def test_resolve_target_none_without_key(settings, monkeypatch):
    settings.frontier.enabled = True
    settings.frontier.providers = [
        FrontierProviderConfig(id="openai", base_url="https://api.openai.com/v1", model="gpt-4o")
    ]
    for name in ("DAARI_FRONTIER_API_KEY", "OPENAI_API_KEY", "OPENROUTER_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    assert resolve_moderations_target(settings) is None


@pytest.mark.asyncio
async def test_disabled_frontier_returns_501(settings):
    settings.frontier.enabled = False
    app = _app(settings)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/v1/moderations", json={"input": "hello"})

    assert response.status_code == 501
    body = response.json()
    assert body["error"]["type"] == "not_implemented"
    assert "frontier" in body["error"]["message"].lower()


@pytest.mark.asyncio
async def test_forwards_to_frontier_and_returns_results(settings, monkeypatch):
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=_MODERATION_OK)

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
            "/v1/moderations",
            json={"input": "hello world", "model": "omni-moderation-latest"},
        )

    assert response.status_code == 200
    assert response.json()["results"][0]["flagged"] is False
    assert len(seen) == 1
    req = seen[0]
    assert str(req.url) == "https://api.openai.com/v1/moderations"
    assert req.headers["authorization"] == "Bearer sk-test"
    payload = req.read()
    assert b"hello world" in payload
    assert b"omni-moderation-latest" in payload


@pytest.mark.asyncio
async def test_upstream_http_error_propagates(settings, monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            429,
            json={"error": {"type": "rate_limit", "message": "slow down"}},
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
        response = await client.post("/v1/moderations", json={"input": ["a", "b"]})

    assert response.status_code == 429
    assert response.json()["error"]["type"] == "rate_limit"
