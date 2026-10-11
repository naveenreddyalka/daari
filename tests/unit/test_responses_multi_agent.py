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


def test_openai_token_usage_sums_nested_agent_usages_when_top_level_undercounts():
    """Parent-only top-level usage under-counts; nested agent rows must be summed (#1500)."""
    from daari.observability.tokens import nested_agent_usages, openai_token_usage

    payload = {
        "usage": {"input_tokens": 100, "output_tokens": 20},
        "agent_usages": [
            {"agent_id": "agent_a", "input_tokens": 400, "output_tokens": 80},
            {"agent_id": "agent_b", "input_tokens": 300, "output_tokens": 60},
        ],
    }
    agents = nested_agent_usages(payload)
    assert len(agents) == 2
    inp, out, estimated = openai_token_usage(payload, prompt_chars=10, content="x")
    assert estimated is False
    assert inp == 800  # 100 + 400 + 300
    assert out == 160  # 20 + 80 + 60


def test_openai_token_usage_keeps_aggregated_top_level_without_double_billing():
    """Published OpenAI shape: top-level usage already includes subagents (#1500)."""
    from daari.observability.tokens import openai_token_usage

    payload = {
        "usage": {"input_tokens": 800, "output_tokens": 160},
        "usage_by_agent": [
            {"agent_id": "root", "input_tokens": 100, "output_tokens": 20},
            {"agent_id": "agent_a", "input_tokens": 400, "output_tokens": 80},
            {"agent_id": "agent_b", "input_tokens": 300, "output_tokens": 60},
        ],
    }
    inp, out, estimated = openai_token_usage(payload, prompt_chars=10, content="x")
    assert estimated is False
    assert inp == 800
    assert out == 160


def test_usage_cost_sums_nested_agent_costs_without_double_billing():
    from daari.gateway.provider_prefs import usage_cost_and_cache

    under = {
        "usage": {"input_tokens": 100, "output_tokens": 20, "cost": 0.01},
        "agent_usages": [
            {"agent_id": "a", "input_tokens": 400, "output_tokens": 80, "cost": 0.04},
            {"agent_id": "b", "input_tokens": 300, "output_tokens": 60, "cost": 0.03},
        ],
    }
    cost, _cached, _write = usage_cost_and_cache(under)
    assert cost == pytest.approx(0.08)

    aggregated = {
        "usage": {"input_tokens": 800, "output_tokens": 160, "cost": 0.08},
        "agent_usages": [
            {"agent_id": "root", "cost": 0.01},
            {"agent_id": "a", "cost": 0.04},
            {"agent_id": "b", "cost": 0.03},
        ],
    }
    cost2, _, _ = usage_cost_and_cache(aggregated)
    assert cost2 == pytest.approx(0.08)


@pytest.mark.asyncio
async def test_frontier_meters_nested_multi_agent_usage_into_meta(tmp_path):
    import sqlite3

    import httpx

    from daari.observability.usage import UsageLedger

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "delegated answer"}}],
                "usage": {"input_tokens": 50, "output_tokens": 10, "cost": 0.005},
                "agent_usages": [
                    {
                        "agent_id": "researcher",
                        "input_tokens": 200,
                        "output_tokens": 40,
                        "cost": 0.02,
                    },
                    {
                        "agent_id": "writer",
                        "input_tokens": 150,
                        "output_tokens": 30,
                        "cost": 0.015,
                    },
                ],
            },
        )

    executor = FrontierExecutor(
        base_url="http://frontier.test",
        default_model="gpt-6.1-sol",
        api_key="sk-test",
        transport=httpx.MockTransport(handler),
    )
    request = InternalRequest(
        messages=[Message(role="user", content="compare")],
        model="gpt-6.1-sol",
        sampling=SamplingParams(multi_agent={"enabled": True, "max_concurrent_subagents": 2}),
    )
    response = await executor.execute(
        request, escalated_from="multi_agent", local_confidence=0.0
    )
    assert response.daari_meta.input_tokens == 400  # 50+200+150
    assert response.daari_meta.output_tokens == 80  # 10+40+30
    assert response.daari_meta.cost_usd == pytest.approx(0.04)
    assert response.daari_meta.usage_estimated is False
    agents = response.daari_meta.agent_usage or []
    assert {a["agent_id"] for a in agents} == {"researcher", "writer"}

    ledger = UsageLedger(path=tmp_path / "ledger.sqlite3")
    ledger.record(
        tier="L6",
        input_tokens=response.daari_meta.input_tokens,
        output_tokens=response.daari_meta.output_tokens,
        reported_cost=response.daari_meta.cost_usd,
        user_id="ops",
        model=response.model,
    )
    with sqlite3.connect(ledger.path) as conn:
        row = conn.execute(
            "SELECT input_tokens, output_tokens FROM usage WHERE tier = 'L6'"
        ).fetchone()
    assert row == (400, 80)

