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



def test_nested_agent_usages_copies_declared_model_and_aliases():
    """Subagent rows carry ``model`` (and model_id / agent.model aliases) (#1553)."""
    from daari.observability.tokens import nested_agent_usages

    payload = {
        "usage": {"input_tokens": 800, "output_tokens": 160},
        "agent_usages": [
            {"agent_id": "root", "input_tokens": 100, "output_tokens": 20},
            {
                "agent_id": "researcher",
                "model": "gpt-6-luna",
                "input_tokens": 400,
                "output_tokens": 80,
            },
            {
                "agent_id": "writer",
                "model_id": "gpt-6.1-sol",
                "input_tokens": 200,
                "output_tokens": 40,
            },
            {
                "agent_id": "critic",
                "agent": {"model": "claude-haiku-5-5"},
                "input_tokens": 100,
                "output_tokens": 20,
            },
        ],
    }
    rows = {row["agent_id"]: row for row in nested_agent_usages(payload)}
    assert "model" not in rows["root"]
    assert rows["researcher"]["model"] == "gpt-6-luna"
    assert rows["writer"]["model"] == "gpt-6.1-sol"
    assert rows["critic"]["model"] == "claude-haiku-5-5"


def test_nested_agent_usages_reads_model_from_output_items():
    from daari.observability.tokens import nested_agent_usages

    payload = {
        "output": [
            {
                "id": "msg_1",
                "agent": {"agent_id": "planner", "model": "gpt-6-luna"},
                "usage": {"input_tokens": 50, "output_tokens": 5},
            }
        ]
    }
    rows = nested_agent_usages(payload)
    assert rows == [
        {"agent_id": "planner", "input_tokens": 50, "output_tokens": 5, "model": "gpt-6-luna"}
    ]


def test_ledger_record_bills_nested_rows_at_declared_model_rate(tmp_path, settings):
    """Catalog-billed multi_agent spend prices each subagent at its own model (#1553)."""
    from daari.config.settings import ModelPrice, PricingSettings
    from daari.observability.usage import UsageLedger
    from daari.pricing import cost_breakdown

    pricing = PricingSettings(
        models={
            "parent-model": ModelPrice(input_per_1m=10.0, output_per_1m=30.0),
            "cheap-sub": ModelPrice(input_per_1m=1.0, output_per_1m=2.0),
            "pricey-sub": ModelPrice(input_per_1m=100.0, output_per_1m=200.0),
        }
    )
    settings = settings.model_copy(
        update={
            "pricing": pricing,
            "usage": settings.usage.model_copy(update={"db_path": str(tmp_path / "usage.db")}),
        }
    )
    ctx = AppContext.from_settings(settings)
    ctx.router.usage_ledger = UsageLedger(tmp_path / "usage.db")
    fallback = float(settings.usage.frontier_price_per_1k_tokens or 0.002)
    request = InternalRequest(
        messages=[Message(role="user", content="delegate")],
        model="parent-model",
        sampling=SamplingParams(multi_agent={"enabled": True}),
    )
    agent_usage = [
        {"agent_id": "root", "input_tokens": 100_000, "output_tokens": 20_000},
        {
            "agent_id": "a",
            "model": "cheap-sub",
            "input_tokens": 400_000,
            "output_tokens": 80_000,
        },
        {
            "agent_id": "b",
            "model": "pricey-sub",
            "input_tokens": 300_000,
            "output_tokens": 60_000,
        },
    ]
    response = InternalResponse(
        content="ok",
        model="parent-model",
        daari_meta=DaariMeta(
            tier="L6",
            executor="frontier",
            model="parent-model",
            input_tokens=800_000,
            output_tokens=160_000,
            usage_estimated=False,
            agent_usage=agent_usage,
        ),
    )
    ctx.router._ledger_record(request, response)

    kw = dict(pricing=pricing, fallback_per_1k=fallback)
    root = cost_breakdown("parent-model", 100_000, 20_000, **kw)
    a = cost_breakdown("cheap-sub", 400_000, 80_000, **kw)
    b = cost_breakdown("pricey-sub", 300_000, 60_000, **kw)
    parent_only = cost_breakdown("parent-model", 800_000, 160_000, **kw)
    expected = root.total + a.total + b.total
    assert expected != pytest.approx(parent_only.total)
    assert response.daari_meta.cost_usd == pytest.approx(expected)
    assert response.daari_meta.cost_input_usd == pytest.approx(
        root.input_usd + a.input_usd + b.input_usd
    )
    assert response.daari_meta.cost_output_usd == pytest.approx(
        root.output_usd + a.output_usd + b.output_usd
    )
    rows = {row["agent_id"]: row for row in response.daari_meta.agent_usage}
    assert rows["a"]["model"] == "cheap-sub"
    assert rows["a"]["cost_usd"] == pytest.approx(a.total)
    assert rows["b"]["cost_usd"] == pytest.approx(b.total)
    # Undeclared model → parent rate.
    assert rows["root"]["cost_usd"] == pytest.approx(root.total)
    assert "model" not in rows["root"]

    import sqlite3

    with sqlite3.connect(ctx.router.usage_ledger.path) as conn:
        row = conn.execute(
            "SELECT model, input_tokens, output_tokens FROM usage WHERE tier = 'L6'"
        ).fetchone()
    assert row == ("parent-model", 800_000, 160_000)


def test_ledger_record_keeps_provider_cost_for_nested_rows(settings, tmp_path):
    """Provider-reported usage.cost still wins over catalog math (#1500 / #1553)."""
    from daari.observability.usage import UsageLedger

    ctx = AppContext.from_settings(settings)
    ctx.router.usage_ledger = UsageLedger(tmp_path / "usage.db")
    request = InternalRequest(
        messages=[Message(role="user", content="delegate")], model="gpt-6.1-sol"
    )
    response = InternalResponse(
        content="ok",
        model="gpt-6.1-sol",
        daari_meta=DaariMeta(
            tier="L6",
            executor="frontier",
            model="gpt-6.1-sol",
            input_tokens=800,
            output_tokens=160,
            cost_usd=0.08,
            agent_usage=[
                {"agent_id": "a", "model": "gpt-6-luna", "input_tokens": 400, "output_tokens": 80}
            ],
        ),
    )
    ctx.router._ledger_record(request, response)
    assert response.daari_meta.cost_usd == pytest.approx(0.08)


@pytest.mark.asyncio
async def test_frontier_exposes_subagent_model_on_agent_usage():
    import httpx

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "delegated"}}],
                "usage": {"input_tokens": 250, "output_tokens": 50},
                "agent_usages": [
                    {
                        "agent_id": "researcher",
                        "model": "gpt-6-luna",
                        "input_tokens": 200,
                        "output_tokens": 40,
                    }
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
        sampling=SamplingParams(multi_agent={"enabled": True}),
    )
    response = await executor.execute(request, escalated_from="multi_agent", local_confidence=0.0)
    assert response.daari_meta.cost_usd is None  # no provider cost → catalog bills later
    assert response.daari_meta.input_tokens == 250
    assert response.daari_meta.agent_usage == [
        {
            "agent_id": "researcher",
            "input_tokens": 200,
            "output_tokens": 40,
            "model": "gpt-6-luna",
        }
    ]
