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
    # Images meter as L6 so per-key budgets see the spend (#2249).
    assert rows[0]["tier"] == "L6"
    assert rows[0]["provider"] == "images"
    assert rows[0]["key_id"] == key.key.key_id
    assert rows[0]["team_id"] == key.key.team_id
    assert rows[0]["model"] == "dall-e-3"
    assert float(rows[0]["cost_usd"]) > 0.0


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
    # No upstream usage → documented per-image estimate (not silent $0) (#2249).
    assert float(response.headers[COST_HEADER]) > 0.0
    ledger = app.state.ctx.router.spend_ledger
    rows = list(ledger.iter_rows(since="2000-01-01T00:00:00+00:00"))
    assert len(rows) == 1
    assert float(rows[0]["cost_usd"]) == float(response.headers[COST_HEADER])


@pytest.mark.asyncio
async def test_usage_block_prices_via_catalog(settings, tmp_path, monkeypatch):
    """GPT-Image-style usage → ledger/headers use pricing.models rates (#2249)."""
    from daari.gateway.cost_headers import COST_HEADER
    from daari.pricing import cost_usd

    body = {
        **_IMAGE_OK,
        "usage": {
            "input_tokens": 1_000,
            "output_tokens": 2_000,
            "total_tokens": 3_000,
            "input_tokens_details": {"text_tokens": 400, "image_tokens": 600},
        },
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=body)

    _patch_upstream(monkeypatch, handler)
    _enable_frontier(settings)
    _enable_spend(settings, tmp_path)
    app = _app(settings)
    model = "gpt-image-2.6-flare"
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/images/generations",
            json={"prompt": "a cube", "model": model, "n": 1},
        )
    assert response.status_code == 200, response.text
    # text@5 + image@8 + output@30 per 1M
    expected = (400 / 1_000_000) * 5.0 + (600 / 1_000_000) * 8.0 + (2_000 / 1_000_000) * 30.0
    assert float(response.headers[COST_HEADER]) == pytest.approx(expected)
    rows = _spend_rows(app)
    assert len(rows) == 1
    assert float(rows[0]["cost_usd"]) == pytest.approx(expected)
    assert rows[0]["model"] == model
    # Catalog path without details still matches cost_usd for total input.
    assert cost_usd(
        model, 1_000, 2_000, settings.pricing, fallback_per_1k=0.002
    ) != pytest.approx(expected)


@pytest.mark.asyncio
async def test_no_usage_emits_estimate_event(settings, tmp_path, monkeypatch):
    from daari.gateway.cost_headers import COST_HEADER

    events: list[tuple[str, dict]] = []

    def _capture(event: str, payload: dict | None = None, **kwargs):
        events.append((event, dict(payload or {}) | dict(kwargs)))

    monkeypatch.setattr("daari.gateway.images.log_gateway_event", _capture)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_IMAGE_OK)

    _patch_upstream(monkeypatch, handler)
    _enable_frontier(settings)
    _enable_spend(settings, tmp_path)
    app = _app(settings)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/images/generations",
            json={"prompt": "a cube", "model": "dall-e-3", "n": 2, "quality": "standard"},
        )
    assert response.status_code == 200, response.text
    cost = float(response.headers[COST_HEADER])
    assert cost == pytest.approx(0.08)  # 2 × $0.04 standard
    assert any(name == "images_cost_estimated" for name, _ in events)
    est = next(p for name, p in events if name == "images_cost_estimated")
    assert est["model"] == "dall-e-3"
    assert est["n"] == 2
    assert float(est["cost_usd"]) == pytest.approx(0.08)


@pytest.mark.asyncio
async def test_image_spend_hits_daily_budget(settings, tmp_path, monkeypatch):
    """Budget-capped key that exhausts via images gets the same 402 as chat (#2249)."""
    body = {
        **_IMAGE_OK,
        "usage": {"input_tokens": 0, "output_tokens": 100_000, "total_tokens": 100_000},
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=body)

    _patch_upstream(monkeypatch, handler)
    _enable_frontier(settings)
    _enable_spend(settings, tmp_path)
    settings.server.api_key = "master"
    settings.server.virtual_keys.path = str(tmp_path / "vk.sqlite3")
    store = VirtualKeyStore(settings.virtual_keys_path)
    # gpt-image-2.6-flare output $30/1M × 100k = $3.00; daily cap $1.
    key = store.create("bot", client_id="client-bot", daily_budget_usd=1.0)
    app = _app(settings)
    app.state.virtual_key_store = store
    app.state.ctx.virtual_key_store = store
    headers = {"Authorization": f"Bearer {key.plaintext}"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        first = await client.post(
            "/v1/images/generations",
            json={"prompt": "charge me", "model": "gpt-image-2.6-flare"},
            headers=headers,
        )
        second = await client.post(
            "/v1/images/generations",
            json={"prompt": "blocked", "model": "gpt-image-2.6-flare"},
            headers=headers,
        )
    assert first.status_code == 200, first.text
    assert second.status_code == 402
    assert second.json()["error"]["type"] == "budget_exceeded"


def test_images_default_model_setting(settings):
    from daari.gateway.images import images_default_model

    assert images_default_model(settings) == "gpt-image-2.6-flare"
    settings.frontier.images_default_model = "gpt-image-2.6-sunburst"
    assert images_default_model(settings) == "gpt-image-2.6-sunburst"


def test_gpt_image_26_catalog_rates(settings):
    from daari.pricing import resolve_price

    for name in ("gpt-image-2.6-sunburst", "gpt-image-2.6-flare"):
        price = resolve_price(name, settings.pricing, fallback_per_1k=0.002)
        assert price.is_fallback is False
        assert price.input_per_1m == 5.0
        assert price.output_per_1m == 30.0
