"""X-Daari-Dropped-Params surfaces ignored client knobs (#1013)."""

from __future__ import annotations

import httpx
import pytest
from httpx import ASGITransport, AsyncClient

from daari.config.settings import Settings
from daari.gateway.cost_headers import DROPPED_PARAMS_HEADER, response_cost_headers
from daari.gateway.internal import DaariMeta
from daari.gateway.sampling import SamplingParams
from daari.router.router import AppContext
from daari.server.app import create_app
from tests.conftest import MOCK_MODEL_CONTENT


def test_dropped_param_names_stable_order():
    names = SamplingParams(
        logprobs=True,
        store=True,
        n=3,
        presence_penalty=0.5,
    ).dropped_param_names()
    assert names == ["presence_penalty", "n", "logprobs", "store"]


def test_dropped_param_names_empty_when_nothing_unsupported():
    assert SamplingParams(max_tokens=20, seed=1).dropped_param_names() == []


def test_response_cost_headers_emit_dropped_params():
    meta = DaariMeta(
        tier="L3",
        executor="ollama",
        dropped_params=["logprobs", "store"],
    )
    headers = response_cost_headers(meta, Settings())
    assert headers[DROPPED_PARAMS_HEADER] == "logprobs,store"


def test_response_cost_headers_omit_when_empty():
    meta = DaariMeta(tier="L3", executor="ollama")
    headers = response_cost_headers(meta, Settings())
    assert DROPPED_PARAMS_HEADER not in headers


@pytest.mark.asyncio
async def test_chat_sets_dropped_params_header(settings, tmp_path, monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"message": {"content": MOCK_MODEL_CONTENT}})

    transport = httpx.MockTransport(handler)
    real = httpx.AsyncClient

    def factory(*args, **kwargs):
        kwargs["transport"] = transport
        return real(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", factory)
    settings.cache.l0.enabled = False
    settings.cache.l1.enabled = False
    settings.routing.max_tier_for_chat = "L3"
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/chat/completions",
            json={
                "model": "daari",
                "messages": [{"role": "user", "content": "hello there"}],
                "logprobs": True,
                "store": True,
            },
        )
    assert response.status_code == 200
    dropped = response.headers.get(DROPPED_PARAMS_HEADER)
    assert dropped is not None
    assert "logprobs" in dropped.split(",")
    assert "store" in dropped.split(",")


@pytest.mark.asyncio
async def test_chat_omits_header_when_nothing_dropped(settings, tmp_path, monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"message": {"content": MOCK_MODEL_CONTENT}})

    transport = httpx.MockTransport(handler)
    real = httpx.AsyncClient

    def factory(*args, **kwargs):
        kwargs["transport"] = transport
        return real(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", factory)
    settings.cache.l0.enabled = False
    settings.cache.l1.enabled = False
    settings.routing.max_tier_for_chat = "L3"
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/chat/completions",
            json={
                "model": "daari",
                "messages": [{"role": "user", "content": "hello there"}],
                "max_tokens": 16,
                "seed": 1,
            },
        )
    assert response.status_code == 200
    assert DROPPED_PARAMS_HEADER not in response.headers


@pytest.mark.asyncio
async def test_responses_sets_dropped_params_header(settings):
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)

    async def fake_route(request):
        from daari.gateway.internal import DaariMeta, InternalResponse

        dropped = request.sampling.dropped_param_names()
        return InternalResponse(
            content="ok",
            model="llama3.2:3b",
            daari_meta=DaariMeta(
                tier="L3",
                executor="ollama",
                latency_ms=1,
                dropped_params=dropped or None,
                warning="; ".join(request.sampling.unsupported_locally()) or None,
            ),
        )

    app.state.ctx.router.route = fake_route
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/responses",
            json={
                "model": "daari",
                "input": "hi",
                "logprobs": True,
                "n": 3,
            },
        )
    assert response.status_code == 200
    dropped = response.headers.get(DROPPED_PARAMS_HEADER)
    assert dropped is not None
    assert "logprobs" in dropped.split(",")
    assert "n" in dropped.split(",")
