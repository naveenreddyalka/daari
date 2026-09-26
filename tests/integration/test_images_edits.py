"""Integration pins for POST /v1/images/edits (#1101).

Hermetic ASGI coverage (mocked upstream) with auth middleware enabled —
same convention as test_images.py generations pins.
"""

from __future__ import annotations

import httpx
import pytest
from httpx import ASGITransport, AsyncClient

from daari.config.settings import FrontierProviderConfig
from daari.router.router import AppContext
from daari.server.app import create_app

_PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 24
_EDIT_OK = {
    "created": 1,
    "data": [{"url": "https://cdn.example/edited.png"}],
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


def _patch_images_upstream(monkeypatch, handler) -> None:
    from daari.gateway import images

    images._http = None
    real = httpx.AsyncClient

    class Patched(real):
        def __init__(self, *args, **kwargs):
            if kwargs.get("transport") is None:
                kwargs["transport"] = httpx.MockTransport(handler)
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", Patched)
    monkeypatch.setattr("daari.gateway.images.httpx.AsyncClient", Patched)


def _enable_openai_frontier(settings) -> None:
    settings.frontier.enabled = True
    settings.frontier.providers = [
        FrontierProviderConfig(
            id="openai",
            base_url="https://api.openai.com/v1",
            model="dall-e-2",
            keys=["sk-test"],
        )
    ]


def test_openapi_lists_images_edits(settings):
    schema = create_app(settings).openapi()
    assert "/v1/images/edits" in schema["paths"]
    assert "post" in schema["paths"]["/v1/images/edits"]


@pytest.mark.asyncio
async def test_images_edits_happy_path_with_auth(settings, monkeypatch):
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=_EDIT_OK)

    _patch_images_upstream(monkeypatch, handler)
    _enable_auth(settings)
    _enable_openai_frontier(settings)
    app = _app(settings)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        denied = await client.post(
            "/v1/images/edits",
            data={"prompt": "make it blue", "model": "dall-e-2"},
            files={"image": ("src.png", _PNG, "image/png")},
        )
        response = await client.post(
            "/v1/images/edits",
            data={"prompt": "make it blue", "model": "dall-e-2"},
            files={"image": ("src.png", _PNG, "image/png")},
            headers=_auth_headers(),
        )

    assert denied.status_code == 401
    assert response.status_code == 200
    assert response.json()["data"][0]["url"].startswith("https://")
    assert len(seen) == 1
    assert str(seen[0].url) == "https://api.openai.com/v1/images/edits"


@pytest.mark.asyncio
async def test_images_edits_frontier_disabled_returns_501(settings):
    _enable_auth(settings)
    settings.frontier.enabled = False
    app = _app(settings)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/images/edits",
            data={"prompt": "make it blue"},
            files={"image": ("src.png", _PNG, "image/png")},
            headers=_auth_headers(),
        )

    assert response.status_code == 501
    body = response.json()
    assert body["error"]["type"] == "not_implemented"
    assert "frontier" in body["error"]["message"].lower()
