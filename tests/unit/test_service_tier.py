"""service_tier pricing and forwarding (issue #430)."""

from __future__ import annotations

import pytest

from daari.config.settings import Settings
from daari.gateway.cost_headers import COST_HEADER, response_cost_headers
from daari.gateway.internal import DaariMeta, InternalRequest, InternalResponse, Message
from daari.gateway.sampling import SamplingParams
from daari.pricing import (
    cost_usd,
    resolve_service_tier_for_request,
    service_tier_factor,
)
from daari.router.anthropic_messages import to_anthropic_payload


def test_known_tiers_have_factors():
    assert service_tier_factor("flex") == 0.5
    assert service_tier_factor("priority") == 2.0
    assert service_tier_factor("fast") == 2.0
    assert service_tier_factor("ultrafast") == 6.0
    assert service_tier_factor("standard") == 1.0
    assert service_tier_factor(None) == 1.0
    assert service_tier_factor("default") == 1.0


def test_unknown_tier_is_standard_and_logs(monkeypatch):
    events: list[str] = []
    monkeypatch.setattr(
        "daari.gateway.request_log.log_gateway_event",
        lambda event, payload: events.append(event),
    )
    assert service_tier_factor("turbo") == 1.0
    assert "service_tier_ignored" in events


def test_fast_tier_does_not_log_ignored(monkeypatch):
    """OpenAI Fast mode (former Priority) must bill 2× without service_tier_ignored (#1527)."""
    events: list[str] = []
    monkeypatch.setattr(
        "daari.gateway.request_log.log_gateway_event",
        lambda event, payload: events.append(event),
    )
    assert service_tier_factor("fast") == 2.0
    assert "service_tier_ignored" not in events


def test_ultrafast_tier_does_not_log_ignored(monkeypatch):
    """OpenAI Ultrafast (6× Standard) must not emit service_tier_ignored (#1519)."""
    events: list[str] = []
    monkeypatch.setattr(
        "daari.gateway.request_log.log_gateway_event",
        lambda event, payload: events.append(event),
    )
    assert service_tier_factor("ultrafast") == 6.0
    assert "service_tier_ignored" not in events


def test_ultrafast_cost_matches_six_times_standard_for_supported_models():
    settings = Settings()
    for model in ("gpt-6.1-sol", "gpt-6-astra"):
        standard = cost_usd(
            model, 1_000_000, 0, settings.pricing, fallback_per_1k=0.002
        )
        ultra = cost_usd(
            model,
            1_000_000,
            0,
            settings.pricing,
            fallback_per_1k=0.002,
            service_tier="ultrafast",
        )
        assert ultra == pytest.approx(standard * 6.0)


def test_ultrafast_policy_allows_supported_models_and_regions():
    ok_sol = resolve_service_tier_for_request(
        model="gpt-6.1-sol", service_tier="ultrafast", region_pin="eu"
    )
    ok_astra_us = resolve_service_tier_for_request(
        model="gpt-6-astra", service_tier="ultrafast", region_pin="us"
    )
    assert ok_sol.service_tier == "ultrafast"
    assert ok_sol.warning is None
    assert ok_astra_us.service_tier == "ultrafast"
    assert ok_astra_us.warning is None


def test_ultrafast_policy_downgrades_unsupported_model():
    decision = resolve_service_tier_for_request(
        model="gpt-4o-mini", service_tier="ultrafast", region_pin=None
    )
    assert decision.service_tier is None
    assert decision.warning == "ultrafast_unsupported_model"


def test_ultrafast_policy_downgrades_astra_on_eu_pin():
    decision = resolve_service_tier_for_request(
        model="gpt-6-astra", service_tier="ultrafast", region_pin="eu"
    )
    assert decision.service_tier is None
    assert decision.warning == "ultrafast_eu_unsupported"


def test_flex_halves_and_priority_doubles_standard_cost():
    settings = Settings()
    standard = cost_usd(
        "gpt-4o-mini", 1_000_000, 0, settings.pricing, fallback_per_1k=0.002
    )
    flex = cost_usd(
        "gpt-4o-mini",
        1_000_000,
        0,
        settings.pricing,
        fallback_per_1k=0.002,
        service_tier="flex",
    )
    priority = cost_usd(
        "gpt-4o-mini",
        1_000_000,
        0,
        settings.pricing,
        fallback_per_1k=0.002,
        service_tier="priority",
    )
    fast = cost_usd(
        "gpt-4o-mini",
        1_000_000,
        0,
        settings.pricing,
        fallback_per_1k=0.002,
        service_tier="fast",
    )
    assert standard == pytest.approx(0.15)
    assert flex == pytest.approx(0.075)
    assert priority == pytest.approx(0.30)
    assert fast == pytest.approx(priority)


def test_openai_and_anthropic_bodies_keep_service_tier():
    openai = SamplingParams.from_openai_body({"service_tier": "flex"})
    anthropic = SamplingParams.from_anthropic_body(
        {"max_tokens": 10, "service_tier": "priority"}
    )
    assert openai.service_tier == "flex"
    assert anthropic.service_tier == "priority"
    assert openai.openai_payload()["service_tier"] == "flex"
    assert (
        to_anthropic_payload(
            InternalRequest(
                messages=[Message(role="user", content="hi")],
                model="daari",
                sampling=anthropic,
            ),
            model="claude-sonnet-4-0",
        )["service_tier"]
        == "priority"
    )


def test_http_models_preserve_service_tier():
    """service_tier must survive ChatCompletionRequest / AnthropicRequest validation (#1005)."""
    from daari.gateway.anthropic import AnthropicRequest
    from daari.gateway.openai import ChatCompletionRequest
    from daari.gateway.responses import ResponsesRequest

    openai_req = ChatCompletionRequest.model_validate(
        {
            "model": "gpt-4o-mini",
            "messages": [{"role": "user", "content": "hi"}],
            "service_tier": "priority",
        }
    )
    anthropic_req = AnthropicRequest.model_validate(
        {
            "model": "claude-sonnet-4",
            "messages": [{"role": "user", "content": "hi"}],
            "max_tokens": 10,
            "service_tier": "flex",
        }
    )
    responses_req = ResponsesRequest.model_validate(
        {
            "model": "gpt-4o-mini",
            "input": "hi",
            "service_tier": "fast",
        }
    )
    assert openai_req.service_tier == "priority"
    assert anthropic_req.service_tier == "flex"
    assert responses_req.service_tier == "fast"

    openai = SamplingParams.from_openai_body(openai_req.model_dump())
    anthropic = SamplingParams.from_anthropic_body(anthropic_req.model_dump())
    responses = SamplingParams.from_responses_body(responses_req.model_dump())
    assert openai.service_tier == "priority"
    assert anthropic.service_tier == "flex"
    assert responses.service_tier == "fast"
    assert openai.openai_payload()["service_tier"] == "priority"
    assert responses.openai_payload()["service_tier"] == "fast"
    assert (
        to_anthropic_payload(
            InternalRequest(
                messages=[Message(role="user", content="hi")],
                model="daari",
                sampling=anthropic,
            ),
            model="claude-sonnet-4",
        )["service_tier"]
        == "flex"
    )


def test_cost_header_uses_service_tier():
    settings = Settings()
    meta = DaariMeta(
        tier="L6",
        executor="frontier",
        model="gpt-4o-mini",
        input_tokens=1_000_000,
        output_tokens=0,
        service_tier="flex",
    )
    headers = response_cost_headers(meta, settings)
    assert float(headers[COST_HEADER]) == pytest.approx(0.075)


@pytest.mark.asyncio
async def test_router_warns_and_clears_ultrafast_on_unsupported_model(tmp_path):
    from daari.cache.exact import ExactCache
    from daari.cache.semantic import SemanticCache
    from daari.observability.metrics import Metrics
    from daari.router.router import OllamaExecutor, Router
    from tests.conftest import NoopEmbedder

    executor = OllamaExecutor(
        base_url="http://test", default_model="llama3.2:3b", tier="L3"
    )

    async def fake_execute(request: InternalRequest) -> InternalResponse:
        return InternalResponse(
            content="A confident answer with plenty of length to avoid escalation.",
            model="llama3.2:3b",
            daari_meta=DaariMeta(
                tier="L3", executor="ollama", provider_id="ollama", latency_ms=1
            ),
        )

    executor.execute = fake_execute  # type: ignore[method-assign]
    router = Router(
        cache=ExactCache(str(tmp_path / "l0"), enabled=False),
        semantic_cache=SemanticCache(
            path=str(tmp_path / "l1"), embedder=NoopEmbedder(), enabled=False
        ),
        ollama_l3=executor,
        metrics=Metrics(),
        max_tier_for_chat="L3",
    )
    request = InternalRequest(
        messages=[Message(role="user", content="hello there")],
        model="gpt-4o-mini",
        sampling=SamplingParams(service_tier="ultrafast"),
    )
    response = await router.route(request)
    assert request.sampling.service_tier is None
    assert response.daari_meta.warning == "ultrafast_unsupported_model"


@pytest.mark.asyncio
async def test_router_warns_and_clears_astra_ultrafast_on_eu_pin(tmp_path):
    from daari.cache.exact import ExactCache
    from daari.cache.semantic import SemanticCache
    from daari.observability.metrics import Metrics
    from daari.router.router import OllamaExecutor, Router
    from tests.conftest import NoopEmbedder

    executor = OllamaExecutor(
        base_url="http://test", default_model="llama3.2:3b", tier="L3"
    )

    async def fake_execute(request: InternalRequest) -> InternalResponse:
        return InternalResponse(
            content="A confident answer with plenty of length to avoid escalation.",
            model="gpt-6-astra",
            daari_meta=DaariMeta(
                tier="L3", executor="ollama", provider_id="ollama", latency_ms=1
            ),
        )

    executor.execute = fake_execute  # type: ignore[method-assign]
    router = Router(
        cache=ExactCache(str(tmp_path / "l0"), enabled=False),
        semantic_cache=SemanticCache(
            path=str(tmp_path / "l1"), embedder=NoopEmbedder(), enabled=False
        ),
        ollama_l3=executor,
        metrics=Metrics(),
        max_tier_for_chat="L3",
    )
    request = InternalRequest(
        messages=[Message(role="user", content="hello there")],
        model="gpt-6-astra",
        sampling=SamplingParams(service_tier="ultrafast"),
    )
    request.meta.region_pin = "eu"
    response = await router.route(request)
    assert request.sampling.service_tier is None
    assert response.daari_meta.warning == "ultrafast_eu_unsupported"
