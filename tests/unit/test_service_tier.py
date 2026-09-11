"""service_tier pricing and forwarding (issue #430)."""

from __future__ import annotations

import pytest

from daari.config.settings import Settings
from daari.gateway.cost_headers import COST_HEADER, response_cost_headers
from daari.gateway.internal import DaariMeta
from daari.gateway.sampling import SamplingParams
from daari.pricing import cost_usd, service_tier_factor


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
