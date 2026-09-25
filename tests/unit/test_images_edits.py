"""POST /v1/images/edits L6 passthrough with governance (#1097)."""

from __future__ import annotations

import httpx
import pytest
from httpx import ASGITransport, AsyncClient

from daari.config.settings import FrontierProviderConfig
from daari.router.router import AppContext
from daari.server.app import create_app


def _patch_upstream(monkeypatch, handler):
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
            model="dall-e-2",
            keys=["sk-test"],
        )
    ]


_PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 24

_EDIT_OK = {
    "created": 1_700_000_000,
    "data": [{"url": "https://cdn.example/edited.png"}],
}


def test_openapi_lists_images_edits(settings):
    schema = create_app(settings).openapi()
    assert "/v1/images/edits" in schema["paths"]
    assert "post" in schema["paths"]["/v1/images/edits"]


@pytest.mark.asyncio
async def test_disabled_frontier_returns_501(settings):
    settings.frontier.enabled = False
    app = _app(settings)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/images/edits",
            data={"prompt": "make it blue"},
            files={"image": ("src.png", _PNG, "image/png")},
        )
    assert response.status_code == 501
    assert response.json()["error"]["type"] == "not_implemented"


@pytest.mark.asyncio
async def test_forwards_multipart_to_frontier(settings, monkeypatch):
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=_EDIT_OK)

    _patch_upstream(monkeypatch, handler)
    _enable_frontier(settings)
    app = _app(settings)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/images/edits",
            data={"prompt": "make it blue", "model": "dall-e-2"},
            files={"image": ("src.png", _PNG, "image/png")},
        )
    assert response.status_code == 200, response.text
    assert response.json() == _EDIT_OK
    assert len(seen) == 1
    req = seen[0]
    assert str(req.url) == "https://api.openai.com/v1/images/edits"
    assert b"make it blue" in req.content
    assert b"src.png" in req.content or b"image" in req.content


@pytest.mark.asyncio
async def test_no_frontier_blocks_without_upstream(settings, monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("must not call upstream")

    _patch_upstream(monkeypatch, handler)
    _enable_frontier(settings)
    app = _app(settings)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/images/edits",
            data={"prompt": "blocked"},
            files={"image": ("src.png", _PNG, "image/png")},
            headers={"X-Daari-No-Frontier": "true"},
        )
    assert response.status_code == 403
    assert response.json()["error"]["type"] == "frontier_not_allowed"
