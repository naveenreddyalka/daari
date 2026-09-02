"""Cost-split and savings response headers on the gateways (issue #278)."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from daari.config.settings import Settings
from daari.gateway.cost_headers import (
    CACHE_HEADER,
    COST_AVOIDED_HEADER,
    COST_HEADER,
    TIER_HEADER,
)
from daari.gateway.internal import DaariMeta, InternalRequest, InternalResponse
from daari.router.router import AppContext
from daari.server.app import create_app
from tests.conftest import META_HEADERS, MOCK_MODEL_CONTENT, mock_all_ollama_executors

pytestmark = pytest.mark.asyncio

PAYLOAD = {"model": "llama3.2:3b", "messages": [{"role": "user", "content": "hello there"}]}


def _app(settings):
    application = create_app(settings)
    application.state.ctx = AppContext.from_settings(settings)
    return application


async def _fake_l3(_request: InternalRequest) -> InternalResponse:
    return InternalResponse(
        content=MOCK_MODEL_CONTENT,
        model="llama3.2:3b",
        daari_meta=DaariMeta(tier="L3", executor="ollama", provider_id="ollama", latency_ms=5),
    )


async def test_chat_completions_l0_hit_costs_nothing_and_avoids_frontier_spend(
    settings, monkeypatch
):
    app = _app(settings)
    mock_all_ollama_executors(monkeypatch, app.state.ctx.router, _fake_l3)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        first = await client.post("/v1/chat/completions", json=PAYLOAD, headers=META_HEADERS)
        second = await client.post("/v1/chat/completions", json=PAYLOAD, headers=META_HEADERS)

    assert first.headers[TIER_HEADER] == "L3" == first.json()["daari_meta"]["tier"]
    assert first.headers[CACHE_HEADER] == "miss"
    assert second.headers[TIER_HEADER] == "L0" == second.json()["daari_meta"]["tier"]
    assert second.headers[CACHE_HEADER] == "hit"
    assert second.json()["daari_meta"]["cache_hit"] is True
    for response in (first, second):
        assert float(response.headers[COST_HEADER]) == 0.0
        assert float(response.headers[COST_AVOIDED_HEADER]) > 0.0


async def test_headers_present_without_meta_opt_in(settings, monkeypatch):
    app = _app(settings)
    mock_all_ollama_executors(monkeypatch, app.state.ctx.router, _fake_l3)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/v1/chat/completions", json=PAYLOAD)
    assert "daari_meta" not in response.json()
    assert response.headers[TIER_HEADER] == "L3"
    assert response.headers[CACHE_HEADER] == "miss"


async def test_messages_route_carries_headers_matching_daari_meta(settings, monkeypatch):
    app = _app(settings)
    mock_all_ollama_executors(monkeypatch, app.state.ctx.router, _fake_l3)
    body = {
        "model": "claude-3-5-sonnet",
        "max_tokens": 64,
        "messages": [{"role": "user", "content": "hello there"}],
    }
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/v1/messages", json=body)
    meta = response.json()["daari_meta"]
    assert response.headers[TIER_HEADER] == meta["tier"] == "L3"
    assert response.headers[CACHE_HEADER] == "miss"
    assert float(response.headers[COST_HEADER]) == 0.0
    assert float(response.headers[COST_AVOIDED_HEADER]) > 0.0


@pytest.fixture
def frontier_settings(tmp_path):
    return Settings.model_validate(
        {
            "server": {"host": "127.0.0.1", "port": 11435},
            "models": {"l3": "llama3.2:3b"},
            "ollama": {"base_url": "http://127.0.0.1:11434"},
            "cache": {
                "l0": {"enabled": True, "path": str(tmp_path / "l0")},
                "l1": {"enabled": False, "path": str(tmp_path / "l1")},
            },
            "usage": {"path": str(tmp_path / "usage" / "ledger.sqlite3")},
            "frontier": {
                "enabled": True,
                "provider": "openai",
                "model": "gpt-4o-mini",
                "confidence_threshold": 0.7,
                "base_url": "https://api.openai.com/v1",
            },
        }
    )


async def _low_confidence(_request: InternalRequest) -> InternalResponse:
    return InternalResponse(
        content="no",
        model="llama3.2:3b",
        daari_meta=DaariMeta(tier="L3", executor="ollama", provider_id="ollama", latency_ms=1),
    )


async def test_frontier_serve_reports_spend_and_avoids_nothing(frontier_settings, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key")
    app = _app(frontier_settings)

    async def fake_l6(request: InternalRequest, *, escalated_from: str, local_confidence: float):
        return InternalResponse(
            content="Frontier answer with enough detail for the user.",
            model="gpt-4o-mini",
            daari_meta=DaariMeta(
                tier="L6",
                executor="frontier",
                provider_id="openai",
                model="gpt-4o-mini",
                escalated_from=escalated_from,
                cost_usd=0.0123,
            ),
        )

    mock_all_ollama_executors(monkeypatch, app.state.ctx.router, _low_confidence)
    monkeypatch.setattr(app.state.ctx.router.frontier, "execute", fake_l6)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/chat/completions",
            json={
                "model": "llama3.2:3b",
                "messages": [{"role": "user", "content": "hard question"}],
            },
            headers=META_HEADERS,
        )
    meta = response.json()["daari_meta"]
    assert meta["tier"] == "L6"
    assert response.headers[TIER_HEADER] == "L6"
    assert response.headers[CACHE_HEADER] == "miss"
    assert (
        float(response.headers[COST_HEADER])
        == pytest.approx(meta["cost_usd"])
        == pytest.approx(0.0123)
    )
    assert float(response.headers[COST_AVOIDED_HEADER]) == 0.0


async def test_stream_headers_carry_tier_and_cache_but_no_cost(settings, monkeypatch):
    app = _app(settings)
    calls = 0

    async def fake_stream(_request: InternalRequest):
        nonlocal calls
        calls += 1
        yield {"message": {"content": MOCK_MODEL_CONTENT}, "done": False}
        yield {"message": {"content": ""}, "done": True}

    for attr in ("ollama", "ollama_l3", "ollama_l4", "ollama_l5"):
        executor = getattr(app.state.ctx.router, attr, None)
        if executor is not None:
            monkeypatch.setattr(executor, "stream", fake_stream)

    payload = {**PAYLOAD, "stream": True}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        first = await client.post("/v1/chat/completions", json=payload)
        second = await client.post("/v1/chat/completions", json=payload)

    assert calls == 1
    assert first.headers[TIER_HEADER] == "L3"
    assert first.headers[CACHE_HEADER] == "miss"
    assert second.headers[TIER_HEADER] == "L0"
    assert second.headers[CACHE_HEADER] == "hit"
    for response in (first, second):
        assert response.headers["content-type"].startswith("text/event-stream")
        assert COST_HEADER not in response.headers
        assert COST_AVOIDED_HEADER not in response.headers
        assert "data: [DONE]" in response.text


async def test_messages_stream_headers_carry_tier(settings, monkeypatch):
    app = _app(settings)

    async def fake_stream(_request: InternalRequest):
        yield {"message": {"content": MOCK_MODEL_CONTENT}, "done": False}
        yield {"message": {"content": ""}, "done": True}

    for attr in ("ollama", "ollama_l3", "ollama_l4", "ollama_l5"):
        executor = getattr(app.state.ctx.router, attr, None)
        if executor is not None:
            monkeypatch.setattr(executor, "stream", fake_stream)

    body = {
        "model": "claude-3-5-sonnet",
        "max_tokens": 64,
        "stream": True,
        "messages": [{"role": "user", "content": "hello there"}],
    }
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/v1/messages", json=body)
    assert response.headers[TIER_HEADER] == "L3"
    assert response.headers[CACHE_HEADER] == "miss"
    assert COST_HEADER not in response.headers
    assert "event: message_stop" in response.text
