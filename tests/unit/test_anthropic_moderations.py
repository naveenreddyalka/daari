"""Anthropic-native moderations ingress (#1100)."""

from __future__ import annotations

import httpx
import pytest
from httpx import ASGITransport, AsyncClient

from daari.auth.rate_families import rate_limit_family
from daari.config.settings import FrontierProviderConfig
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


def test_openapi_lists_messages_moderations(settings):
    schema = create_app(settings).openapi()
    assert "/v1/messages/moderations" in schema["paths"]
    assert "post" in schema["paths"]["/v1/messages/moderations"]


def test_rate_family_messages_moderations():
    assert rate_limit_family("/v1/messages/moderations") == "moderations"
    assert rate_limit_family("/v1/messages") == "chat"


@pytest.mark.asyncio
async def test_disabled_frontier_returns_501(settings):
    settings.frontier.enabled = False
    app = _app(settings)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/messages/moderations",
            json={"input": "hello"},
            headers={"anthropic-version": "2023-06-01", "x-api-key": "test"},
        )

    assert response.status_code == 501


@pytest.mark.asyncio
async def test_messages_body_maps_to_upstream(settings, monkeypatch):
    settings.frontier.enabled = True
    settings.frontier.providers = [
        FrontierProviderConfig(
            id="openai",
            base_url="https://api.openai.com/v1",
            model="gpt-4o",
            keys=["sk-test"],
        )
    ]
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        import json

        captured["json"] = json.loads(request.content)
        return httpx.Response(200, json=_MODERATION_OK)

    _patch_upstream(monkeypatch, handler)
    app = _app(settings)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/messages/moderations",
            json={
                "messages": [{"role": "user", "content": "is this safe?"}],
                "model": "omni-moderation-latest",
            },
            headers={"anthropic-version": "2023-06-01", "x-api-key": "test"},
        )

    assert response.status_code == 200
    assert captured["url"] == "https://api.openai.com/v1/moderations"
    assert captured["json"]["input"] == "is this safe?"
    assert response.json()["id"] == "modr-test"


@pytest.mark.asyncio
async def test_input_body_happy_path(settings, monkeypatch):
    settings.frontier.enabled = True
    settings.frontier.providers = [
        FrontierProviderConfig(
            id="openai",
            base_url="https://api.openai.com/v1",
            model="gpt-4o",
            keys=["sk-test"],
        )
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_MODERATION_OK)

    _patch_upstream(monkeypatch, handler)
    app = _app(settings)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/messages/moderations",
            json={"input": ["a", "b"]},
            headers={"anthropic-version": "2023-06-01"},
        )

    assert response.status_code == 200
    assert response.json()["results"][0]["flagged"] is False
