"""W3C baggage → request tags (opt-in routing.baggage_to_tags) (#2153)."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from daari.gateway.internal import DaariMeta, InternalRequest, InternalResponse
from daari.router.router import AppContext
from daari.router.signals import parse_baggage_to_tags, parse_request_tags
from daari.server.app import create_app
from tests.conftest import MOCK_MODEL_CONTENT, mock_all_ollama_executors


def test_parse_baggage_to_tags_keys_as_baggage_prefix():
    assert parse_baggage_to_tags("team=eng,env=prod") == [
        "baggage:env",
        "baggage:team",
    ]


def test_parse_baggage_strips_properties_and_percent_decodes_value_unused():
    # Values are not copied into tags (cardinality); properties after `;` ignored.
    assert parse_baggage_to_tags("userId=alice%40ex.com;private=true") == [
        "baggage:userId",
    ]


def test_parse_baggage_drops_malformed_members():
    assert parse_baggage_to_tags("=novalue,good=1,bad,;,ok=2") == [
        "baggage:good",
        "baggage:ok",
    ]
    assert parse_baggage_to_tags(None) == []
    assert parse_baggage_to_tags("  ,  ") == []
    assert parse_baggage_to_tags("!!!") == []


def test_parse_request_tags_unions_baggage_when_enabled():
    tags = parse_request_tags(
        header="canary",
        metadata={"tags": ["eval"]},
        baggage="team=eng,env=prod",
        baggage_to_tags=True,
    )
    assert tags == ["baggage:env", "baggage:team", "canary", "eval"]


def test_parse_request_tags_ignores_baggage_when_disabled():
    tags = parse_request_tags(
        header="canary",
        baggage="team=eng",
        baggage_to_tags=False,
    )
    assert tags == ["canary"]


@pytest.mark.asyncio
async def test_chat_maps_baggage_into_meta_tags_when_enabled(settings, monkeypatch):
    settings.routing.baggage_to_tags = True
    settings.cache.l0.enabled = False
    settings.cache.l1.enabled = False
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    seen: list[InternalRequest] = []

    async def fake_execute(request: InternalRequest) -> InternalResponse:
        seen.append(request)
        return InternalResponse(
            content=MOCK_MODEL_CONTENT,
            model="llama3.2:3b",
            daari_meta=DaariMeta(
                tier="L3",
                executor="ollama",
                provider_id="ollama:l3",
                latency_ms=1,
            ),
        )

    mock_all_ollama_executors(monkeypatch, app.state.ctx.router, fake_execute)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/v1/chat/completions",
            json={
                "model": "daari",
                "messages": [{"role": "user", "content": "hi"}],
                "metadata": {"tags": ["eval"]},
            },
            headers={
                "X-Daari-Tags": "canary",
                "baggage": "team=eng,env=prod",
            },
        )
    assert response.status_code == 200
    assert seen
    assert seen[0].meta.tags == ["baggage:env", "baggage:team", "canary", "eval"]


@pytest.mark.asyncio
async def test_chat_ignores_baggage_when_disabled(settings, monkeypatch):
    settings.routing.baggage_to_tags = False
    settings.cache.l0.enabled = False
    settings.cache.l1.enabled = False
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    seen: list[InternalRequest] = []

    async def fake_execute(request: InternalRequest) -> InternalResponse:
        seen.append(request)
        return InternalResponse(
            content=MOCK_MODEL_CONTENT,
            model="llama3.2:3b",
            daari_meta=DaariMeta(
                tier="L3",
                executor="ollama",
                provider_id="ollama:l3",
                latency_ms=1,
            ),
        )

    mock_all_ollama_executors(monkeypatch, app.state.ctx.router, fake_execute)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/v1/chat/completions",
            json={
                "model": "daari",
                "messages": [{"role": "user", "content": "hi"}],
            },
            headers={"baggage": "team=eng"},
        )
    assert response.status_code == 200
    assert seen
    assert seen[0].meta.tags == []


@pytest.mark.asyncio
async def test_chat_malformed_baggage_does_not_500(settings, monkeypatch):
    settings.routing.baggage_to_tags = True
    settings.cache.l0.enabled = False
    settings.cache.l1.enabled = False
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)

    async def fake_execute(_request: InternalRequest) -> InternalResponse:
        return InternalResponse(
            content=MOCK_MODEL_CONTENT,
            model="llama3.2:3b",
            daari_meta=DaariMeta(
                tier="L3",
                executor="ollama",
                provider_id="ollama:l3",
                latency_ms=1,
            ),
        )

    mock_all_ollama_executors(monkeypatch, app.state.ctx.router, fake_execute)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/v1/chat/completions",
            json={
                "model": "daari",
                "messages": [{"role": "user", "content": "hi"}],
            },
            headers={"baggage": "=bad,,,;x=y,good=1"},
        )
    assert response.status_code == 200
