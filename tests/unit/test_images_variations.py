"""POST /v1/images/variations L6 passthrough with governance (#1098)."""

from __future__ import annotations

import httpx
import pytest
from httpx import ASGITransport, AsyncClient

from daari.auth.virtual_keys import VirtualKeyStore
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

_VARIATION_OK = {
    "created": 1_700_000_000,
    "data": [{"url": "https://cdn.example/variation.png"}],
}


def test_openapi_lists_images_variations(settings):
    schema = create_app(settings).openapi()
    assert "/v1/images/variations" in schema["paths"]
    assert "post" in schema["paths"]["/v1/images/variations"]


@pytest.mark.asyncio
async def test_disabled_frontier_returns_501(settings):
    settings.frontier.enabled = False
    app = _app(settings)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/images/variations",
            files={"image": ("src.png", _PNG, "image/png")},
        )
    assert response.status_code == 501
    assert response.json()["error"]["type"] == "not_implemented"


@pytest.mark.asyncio
async def test_forwards_multipart_to_frontier(settings, monkeypatch):
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=_VARIATION_OK)

    _patch_upstream(monkeypatch, handler)
    _enable_frontier(settings)
    app = _app(settings)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/images/variations",
            data={"model": "dall-e-2", "n": "1"},
            files={"image": ("src.png", _PNG, "image/png")},
        )
    assert response.status_code == 200, response.text
    assert response.json() == _VARIATION_OK
    assert len(seen) == 1
    req = seen[0]
    assert str(req.url) == "https://api.openai.com/v1/images/variations"
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
            "/v1/images/variations",
            files={"image": ("src.png", _PNG, "image/png")},
            headers={"X-Daari-No-Frontier": "true"},
        )
    assert response.status_code == 403
    assert response.json()["error"]["type"] == "frontier_not_allowed"


@pytest.mark.asyncio
async def test_model_allowlist_blocks(settings, tmp_path, monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("must not call upstream")

    _patch_upstream(monkeypatch, handler)
    _enable_frontier(settings)
    settings.server.api_key = "master"
    settings.server.virtual_keys.path = str(tmp_path / "vk.sqlite3")
    store = VirtualKeyStore(settings.virtual_keys_path)
    locked = store.create("locked", allowed_models=["gpt-4o"])
    app = _app(settings)
    app.state.virtual_key_store = store
    app.state.ctx.virtual_key_store = store

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/images/variations",
            data={"model": "dall-e-2"},
            files={"image": ("src.png", _PNG, "image/png")},
            headers={"Authorization": f"Bearer {locked.plaintext}"},
        )
    assert response.status_code == 403
    assert response.json()["error"]["type"] == "model_not_allowed"


@pytest.mark.asyncio
async def test_region_pin_filters_slots(settings, tmp_path, monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError(f"must not call {request.url}")

    _patch_upstream(monkeypatch, handler)
    settings.frontier.enabled = True
    settings.frontier.providers = [
        FrontierProviderConfig(
            id="us",
            base_url="https://us.example/v1",
            model="dall-e-2",
            keys=["sk-us"],
            region="us",
        )
    ]
    settings.server.api_key = "master"
    settings.server.virtual_keys.path = str(tmp_path / "vk.sqlite3")
    store = VirtualKeyStore(settings.virtual_keys_path)
    pinned = store.create("eu-bot", region_pin="eu")
    app = _app(settings)
    app.state.virtual_key_store = store
    app.state.ctx.virtual_key_store = store

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/images/variations",
            files={"image": ("src.png", _PNG, "image/png")},
            headers={"Authorization": f"Bearer {pinned.plaintext}"},
        )
    assert response.status_code == 400
    assert response.json()["error"]["type"] == "region_unavailable"
