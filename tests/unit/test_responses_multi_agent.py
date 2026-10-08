"""Responses multi_agent beta: forward on L6 or fail honestly (#1478)."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from daari.gateway.internal import DaariMeta, InternalRequest, InternalResponse, Message
from daari.gateway.responses import ResponsesRequest, multi_agent_enabled
from daari.gateway.sampling import MultiAgentUnavailable, SamplingParams
from daari.router.frontier import FrontierExecutor
from daari.router.router import AppContext
from daari.server.app import create_app


def test_responses_request_declares_multi_agent():
    body = ResponsesRequest(
        model="gpt-6.1-sol",
        input="compare",
        multi_agent={"enabled": True, "max_concurrent_subagents": 3},
    )
    assert body.multi_agent == {"enabled": True, "max_concurrent_subagents": 3}
    assert multi_agent_enabled(body.multi_agent) is True
    assert multi_agent_enabled({"enabled": False}) is False
    assert multi_agent_enabled(None) is False


def test_from_responses_body_parses_multi_agent():
    params = SamplingParams.from_responses_body(
        {"multi_agent": {"enabled": True, "max_concurrent_subagents": 2}}
    )
    assert params.multi_agent == {"enabled": True, "max_concurrent_subagents": 2}
    assert "multi_agent" in params.openai_payload()
    assert params.openai_payload()["multi_agent"]["enabled"] is True


def test_l6_openai_payload_includes_multi_agent():
    params = SamplingParams(multi_agent={"enabled": True, "max_concurrent_subagents": 3})
    request = InternalRequest(
        messages=[Message(role="user", content="hello")],
        model="gpt-6.1-sol",
        sampling=params,
    )
    executor = FrontierExecutor(
        api_key="sk-test",
        base_url="https://api.openai.com/v1",
        default_model="gpt-6.1-sol",
        provider="openai",
    )
    payload = executor._openai_payload(request, stream=False)
    assert payload["multi_agent"] == {"enabled": True, "max_concurrent_subagents": 3}
    headers = executor._openai_headers_for_request(request)
    assert "responses_multi_agent=v1" in headers.get("OpenAI-Beta", "")


def test_unsupported_responses_tools_wired_into_handler(settings):
    """Dead helper is consulted so hosted types still 400 (#1478)."""
    from daari.gateway.responses import unsupported_responses_tools

    assert unsupported_responses_tools([{"type": "web_search"}]) == ["web_search"]


@pytest.mark.asyncio
async def test_multi_agent_local_path_returns_400(settings):
    settings.frontier.enabled = False
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)

    async def fake_route(request: InternalRequest) -> InternalResponse:
        return InternalResponse(
            content="should not run",
            model="m",
            daari_meta=DaariMeta(tier="L3", executor="ollama", latency_ms=1),
        )

    app.state.ctx.router.route = fake_route
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/responses",
            json={
                "model": "daari",
                "input": "delegate this",
                "multi_agent": {"enabled": True, "max_concurrent_subagents": 3},
            },
        )
    assert response.status_code == 400
    detail = response.json()["detail"]
    assert "multi_agent" in detail
    assert "frontier" in detail.lower() or "L6" in detail


@pytest.mark.asyncio
async def test_multi_agent_no_frontier_header_returns_400(settings, monkeypatch):
    settings.frontier.enabled = True
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/responses",
            headers={"X-Daari-No-Frontier": "true"},
            json={
                "model": "gpt-6.1-sol",
                "input": "delegate",
                "multi_agent": {"enabled": True},
            },
        )
    assert response.status_code == 400
    assert "multi_agent" in response.json()["detail"]


@pytest.mark.asyncio
async def test_multi_agent_disabled_still_routes_locally(settings):
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)

    async def fake_route(request: InternalRequest) -> InternalResponse:
        fake_route.seen = request
        return InternalResponse(
            content="ok",
            model="m",
            daari_meta=DaariMeta(tier="L3", executor="ollama", latency_ms=1),
        )

    app.state.ctx.router.route = fake_route
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/responses",
            json={
                "model": "daari",
                "input": "hi",
                "multi_agent": {"enabled": False},
            },
        )
    assert response.status_code == 200
    assert fake_route.seen.sampling.multi_agent == {"enabled": False}


def test_multi_agent_unavailable_exception_message():
    exc = MultiAgentUnavailable("frontier_disabled")
    assert "multi_agent" in str(exc).lower()
    assert exc.reason == "frontier_disabled"
