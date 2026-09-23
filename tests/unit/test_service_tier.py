"""service_tier pricing and forwarding (issue #430)."""

from __future__ import annotations

import pytest

from daari.config.settings import Settings
from daari.gateway.cost_headers import COST_HEADER, response_cost_headers
from daari.gateway.internal import DaariMeta, InternalRequest, Message
from daari.gateway.sampling import SamplingParams
from daari.pricing import cost_usd, service_tier_factor
from daari.router.anthropic_messages import to_anthropic_payload


def test_known_tiers_have_factors():
    assert service_tier_factor("flex") == 0.5
    assert service_tier_factor("priority") == 2.0
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
    assert standard == pytest.approx(0.15)
    assert flex == pytest.approx(0.075)
    assert priority == pytest.approx(0.30)


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
    assert openai_req.service_tier == "priority"
    assert anthropic_req.service_tier == "flex"

    openai = SamplingParams.from_openai_body(openai_req.model_dump())
    anthropic = SamplingParams.from_anthropic_body(anthropic_req.model_dump())
    assert openai.service_tier == "priority"
    assert anthropic.service_tier == "flex"
    assert openai.openai_payload()["service_tier"] == "priority"
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
