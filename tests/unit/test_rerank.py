"""POST /v1/rerank L6 passthrough (#1051) + governance (#1058)."""

from __future__ import annotations

import httpx
import pytest
from httpx import ASGITransport, AsyncClient

from daari.auth.virtual_keys import VirtualKeyStore
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


def _enable_frontier(settings):
    settings.frontier.enabled = True
    settings.frontier.providers = [
        FrontierProviderConfig(
            id="cohere",
            base_url="https://api.cohere.ai/v1",
            model="rerank-english-v3.0",
            keys=["sk-test"],
        )
    ]


def _enable_spend(settings, tmp_path):
    settings.usage.spend.enabled = True
    settings.usage.spend.path = str(tmp_path / "spend.sqlite3")


def _spend_rows(app):
    ledger = app.state.ctx.router.spend_ledger
    return list(ledger.iter_rows(since="2000-01-01T00:00:00+00:00"))


@pytest.mark.asyncio
async def test_tier_cap_blocks_rerank_without_upstream(settings, tmp_path, monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("must not call upstream")

    _patch_upstream(monkeypatch, handler)
    _enable_frontier(settings)
    settings.server.api_key = "master"
    settings.server.virtual_keys.path = str(tmp_path / "vk.sqlite3")
    store = VirtualKeyStore(settings.virtual_keys_path)
    capped = store.create("local", client_id="local-bot", tier_cap="L4")
    app = _app(settings)
    app.state.virtual_key_store = store
    app.state.ctx.virtual_key_store = store

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/rerank",
            json={"query": "q", "documents": ["a", "b"]},
            headers={"Authorization": f"Bearer {capped.plaintext}"},
        )
    assert response.status_code == 403
    assert response.json()["error"]["type"] == "frontier_not_allowed"


@pytest.mark.asyncio
async def test_no_frontier_header_blocks_rerank(settings, monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("must not call upstream")

    _patch_upstream(monkeypatch, handler)
    _enable_frontier(settings)
    app = _app(settings)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/rerank",
            json={"query": "q", "documents": ["a"]},
            headers={"X-Daari-No-Frontier": "true"},
        )
    assert response.status_code == 403
    assert response.json()["error"]["type"] == "frontier_not_allowed"


@pytest.mark.asyncio
async def test_model_allowlist_blocks_rerank(settings, tmp_path, monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("must not call upstream")

    _patch_upstream(monkeypatch, handler)
    _enable_frontier(settings)
    settings.server.api_key = "master"
    settings.server.virtual_keys.path = str(tmp_path / "vk.sqlite3")
    store = VirtualKeyStore(settings.virtual_keys_path)
    locked = store.create("locked", allowed_models=["gpt-4o-mini"])
    app = _app(settings)
    app.state.virtual_key_store = store
    app.state.ctx.virtual_key_store = store

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/rerank",
            json={
                "query": "q",
                "documents": ["a"],
                "model": "rerank-english-v3.0",
            },
            headers={"Authorization": f"Bearer {locked.plaintext}"},
        )
    assert response.status_code == 403
    assert response.json()["error"]["type"] == "model_not_allowed"


@pytest.mark.asyncio
async def test_rerank_writes_spend_row(settings, tmp_path, monkeypatch):
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=_RERANK_OK)

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
            "/v1/rerank",
            json={
                "query": "stripe deal",
                "documents": ["unrelated", "stripe acquired openrouter"],
                "model": "rerank-english-v3.0",
            },
            headers={"Authorization": f"Bearer {key.plaintext}"},
        )
    assert response.status_code == 200, response.text
    assert len(seen) == 1
    rows = _spend_rows(app)
    assert len(rows) == 1
    assert rows[0]["tier"] == "rerank"
    assert rows[0]["key_id"] == key.key.key_id
    assert rows[0]["team_id"] == key.key.team_id
    assert rows[0]["model"] == "rerank-english-v3.0"
    assert rows[0]["input_tokens"] == 2  # Cohere-style search units = doc count


def _fast_retry(settings):
    settings.upstream.retry.attempts = 3
    settings.upstream.retry.base_delay_ms = 0
    settings.upstream.retry.max_delay_ms = 0
    settings.upstream.retry.jitter = 0.0


@pytest.mark.asyncio
async def test_rerank_retries_then_succeeds(settings, monkeypatch):
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] < 3:
            return httpx.Response(502, json={"error": {"type": "busy", "message": "busy"}})
        return httpx.Response(200, json=_RERANK_OK)

    _patch_upstream(monkeypatch, handler)
    _enable_frontier(settings)
    _fast_retry(settings)
    app = _app(settings)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/rerank",
            json={"query": "q", "documents": ["a"]},
        )
    assert response.status_code == 200, response.text
    assert calls["n"] == 3


@pytest.mark.asyncio
async def test_rerank_slot_failover(settings, monkeypatch):
    seen_hosts: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_hosts.append(request.url.host)
        if request.url.host == "primary.example":
            return httpx.Response(503, json={"error": {"type": "busy", "message": "down"}})
        return httpx.Response(200, json=_RERANK_OK)

    _patch_upstream(monkeypatch, handler)
    settings.frontier.enabled = True
    settings.frontier.providers = [
        FrontierProviderConfig(
            id="primary",
            base_url="https://primary.example/v1",
            model="rerank-a",
            keys=["sk-a"],
            retry_attempts=1,
        ),
        FrontierProviderConfig(
            id="secondary",
            base_url="https://secondary.example/v1",
            model="rerank-b",
            keys=["sk-b"],
            retry_attempts=1,
        ),
    ]
    app = _app(settings)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/rerank",
            json={"query": "q", "documents": ["a"]},
        )
    assert response.status_code == 200, response.text
    assert seen_hosts[0] == "primary.example"
    assert "secondary.example" in seen_hosts


@pytest.mark.asyncio
async def test_rerank_region_pin_filters_slots(settings, tmp_path, monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError(f"must not call {request.url}")

    _patch_upstream(monkeypatch, handler)
    settings.frontier.enabled = True
    settings.frontier.providers = [
        FrontierProviderConfig(
            id="us",
            base_url="https://us.example/v1",
            model="rerank",
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
            "/v1/rerank",
            json={"query": "q", "documents": ["a"]},
            headers={"Authorization": f"Bearer {pinned.plaintext}"},
        )
    assert response.status_code == 400
    assert response.json()["error"]["type"] == "region_unavailable"


@pytest.mark.asyncio
async def test_rerank_include_response_cost_headers(settings, tmp_path, monkeypatch):
    from daari.gateway.cost_headers import COST_HEADER, TIER_HEADER

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_RERANK_OK)

    _patch_upstream(monkeypatch, handler)
    _enable_frontier(settings)
    settings.usage.spend.enabled = True
    settings.usage.spend.path = str(tmp_path / "spend.sqlite3")
    app = _app(settings)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/rerank",
            json={"query": "q", "documents": ["a", "b"]},
        )
    assert response.status_code == 200, response.text
    assert response.headers[TIER_HEADER] == "rerank"
    assert float(response.headers[COST_HEADER]) == 0.0
    ledger = app.state.ctx.router.spend_ledger
    rows = list(ledger.iter_rows(since="2000-01-01T00:00:00+00:00"))
    assert len(rows) == 1
    assert float(rows[0]["cost_usd"]) == float(response.headers[COST_HEADER])

