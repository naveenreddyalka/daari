"""POST /v1/images/generations L6 passthrough with governance (#1064)."""

from __future__ import annotations

import httpx
import pytest
from httpx import ASGITransport, AsyncClient

from daari.auth.virtual_keys import VirtualKeyStore
from daari.config.settings import FrontierProviderConfig
from daari.gateway.images import resolve_images_target
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


_IMAGE_OK = {
    "created": 1_700_000_000,
    "data": [{"url": "https://cdn.example/generated.png"}],
}


def _enable_frontier(settings):
    settings.frontier.enabled = True
    settings.frontier.providers = [
        FrontierProviderConfig(
            id="openai",
            base_url="https://api.openai.com/v1",
            model="dall-e-3",
            keys=["sk-test"],
        )
    ]


def _enable_spend(settings, tmp_path):
    settings.usage.spend.enabled = True
    settings.usage.spend.path = str(tmp_path / "spend.sqlite3")


def _spend_rows(app):
    ledger = app.state.ctx.router.spend_ledger
    return list(ledger.iter_rows(since="2000-01-01T00:00:00+00:00"))


def test_openapi_lists_images_generations(settings):
    schema = create_app(settings).openapi()
    assert "/v1/images/generations" in schema["paths"]
    assert "post" in schema["paths"]["/v1/images/generations"]


def test_resolve_target_none_when_frontier_disabled(settings):
    settings.frontier.enabled = False
    assert resolve_images_target(settings) is None


@pytest.mark.asyncio
async def test_disabled_frontier_returns_501(settings):
    settings.frontier.enabled = False
    app = _app(settings)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/images/generations",
            json={"prompt": "a cat"},
        )
    assert response.status_code == 501
    assert response.json()["error"]["type"] == "not_implemented"


@pytest.mark.asyncio
async def test_forwards_to_frontier_and_returns_data(settings, monkeypatch):
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=_IMAGE_OK)

    _patch_upstream(monkeypatch, handler)
    _enable_frontier(settings)
    app = _app(settings)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/images/generations",
            json={
                "prompt": "a red cube",
                "model": "dall-e-3",
                "n": 1,
                "size": "1024x1024",
                "quality": "standard",
                "response_format": "url",
                "user": "dev",
            },
        )

    assert response.status_code == 200, response.text
    assert response.json()["data"][0]["url"].endswith("generated.png")
    assert len(seen) == 1
    req = seen[0]
    assert str(req.url) == "https://api.openai.com/v1/images/generations"
    assert req.headers["authorization"] == "Bearer sk-test"
    payload = req.read()
    assert b"a red cube" in payload
    assert b"dall-e-3" in payload
    assert b"1024x1024" in payload


@pytest.mark.asyncio
async def test_no_frontier_blocks_without_upstream(settings, monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("must not call upstream")

    _patch_upstream(monkeypatch, handler)
    _enable_frontier(settings)
    app = _app(settings)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/images/generations",
            json={"prompt": "blocked"},
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
            "/v1/images/generations",
            json={"prompt": "blocked", "model": "dall-e-3"},
            headers={"Authorization": f"Bearer {locked.plaintext}"},
        )
    assert response.status_code == 403
    assert response.json()["error"]["type"] == "model_not_allowed"


@pytest.mark.asyncio
async def test_success_writes_spend_ledger_row(settings, tmp_path, monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_IMAGE_OK)

    _patch_upstream(monkeypatch, handler)
    _enable_frontier(settings)
    _enable_spend(settings, tmp_path)
    settings.server.api_key = "master"
    settings.server.virtual_keys.path = str(tmp_path / "vk.sqlite3")
    store = VirtualKeyStore(settings.virtual_keys_path)
    key = store.create("bot", client_id="client-bot", team="eng")
    app = _app(settings)
    app.state.virtual_key_store = store
    app.state.ctx.virtual_key_store = store

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/images/generations",
            json={"prompt": "charge me", "model": "dall-e-3"},
            headers={"Authorization": f"Bearer {key.plaintext}"},
        )
    assert response.status_code == 200, response.text
    rows = _spend_rows(app)
    assert len(rows) == 1
    assert rows[0]["tier"] == "images"
    assert rows[0]["key_id"] == key.key.key_id
    assert rows[0]["team_id"] == key.key.team_id
    assert rows[0]["model"] == "dall-e-3"


@pytest.mark.asyncio
async def test_images_include_response_cost_headers(settings, tmp_path, monkeypatch):
    from daari.gateway.cost_headers import COST_HEADER, TIER_HEADER

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_IMAGE_OK)

    _patch_upstream(monkeypatch, handler)
    _enable_frontier(settings)
    settings.usage.spend.enabled = True
    settings.usage.spend.path = str(tmp_path / "spend.sqlite3")
    app = _app(settings)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/images/generations",
            json={"prompt": "a cube", "model": "dall-e-3"},
        )
    assert response.status_code == 200, response.text
    assert response.headers[TIER_HEADER] == "images"
    assert float(response.headers[COST_HEADER]) == 0.0
    ledger = app.state.ctx.router.spend_ledger
    rows = list(ledger.iter_rows(since="2000-01-01T00:00:00+00:00"))
    assert len(rows) == 1
    assert float(rows[0]["cost_usd"]) == float(response.headers[COST_HEADER])
