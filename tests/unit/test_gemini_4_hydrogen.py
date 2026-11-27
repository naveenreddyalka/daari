"""Gemini 4 Hydrogen catalog rates, capabilities, and xhigh (#2359)."""

from __future__ import annotations

from pathlib import Path

import pytest

from daari.config.settings import Settings, SignalOverrideRule
from daari.gateway.internal import InternalRequest, Message
from daari.gateway.sampling import (
    ACCEPTED_REASONING_EFFORTS,
    SamplingParams,
)
from daari.pricing import cost_usd, matching_model_key, resolve_price, service_tier_factor
from daari.router.capabilities import known_model_capabilities
from daari.router.frontier import FrontierExecutor
from daari.router.signals import apply_signal_override
from daari.router.profile import build_prompt_profile

BUDGETS = Path("docs/developer/guides/configuration/budgets-frontier.md")
COMPARE = Path("docs/developer/resources/compare-litellm.md")


def test_hydrogen_list_price_and_vendor_alias():
    settings = Settings()
    price = resolve_price(
        "models/gemini-4-hydrogen", settings.pricing, fallback_per_1k=0.002
    )
    assert price.is_fallback is False
    assert price.input_per_1m == pytest.approx(1.50)
    assert price.output_per_1m == pytest.approx(7.50)
    assert price.cached_input_per_1m == pytest.approx(0.075)
    assert matching_model_key("models/gemini-4-hydrogen", settings.pricing.models) == (
        "gemini-4-hydrogen"
    )


def test_hydrogen_key_beats_a_gemini_4_prefix():
    table = {
        "gemini-4": {"input_per_1m": 9.0, "output_per_1m": 9.0},
        "gemini-4-carbon": {"input_per_1m": 4.0, "output_per_1m": 20.0},
        "gemini-4-hydrogen": {"input_per_1m": 1.5, "output_per_1m": 7.5},
    }
    assert matching_model_key("gemini-4-hydrogen", table) == "gemini-4-hydrogen"
    assert matching_model_key("models/gemini-4-hydrogen", table) == "gemini-4-hydrogen"
    assert matching_model_key("gemini-4-carbon", table) == "gemini-4-carbon"


def test_hydrogen_priority_is_1_8_and_flex_is_half():
    settings = Settings()
    base = cost_usd(
        "gemini-4-hydrogen",
        1_000_000,
        0,
        settings.pricing,
        fallback_per_1k=0.002,
    )
    priority = cost_usd(
        "models/gemini-4-hydrogen",
        1_000_000,
        0,
        settings.pricing,
        fallback_per_1k=0.002,
        service_tier="priority",
    )
    flex = cost_usd(
        "gemini-4-hydrogen",
        1_000_000,
        0,
        settings.pricing,
        fallback_per_1k=0.002,
        service_tier="flex",
    )
    assert base == pytest.approx(1.50)
    assert priority == pytest.approx(1.50 * 1.8)
    assert flex == pytest.approx(0.75)
    assert service_tier_factor("priority") == 2.0
    assert service_tier_factor("priority", "gemini-4-carbon") == 2.0
    assert service_tier_factor("priority", "gemini-4-hydrogen") == 1.8


def test_hydrogen_capabilities_match_carbon_and_argon():
    hydrogen = known_model_capabilities("gemini-4-hydrogen")
    carbon = known_model_capabilities("gemini-4-carbon")
    assert hydrogen == carbon
    assert {"tools", "json", "vision", "audio", "long_context"} <= set(hydrogen)
    assert known_model_capabilities("models/gemini-4-hydrogen") == hydrogen


def test_xhigh_is_accepted_and_forwarded_on_hydrogen_only_locally_omitted():
    assert "xhigh" in ACCEPTED_REASONING_EFFORTS
    params = SamplingParams.from_openai_body({"reasoning_effort": "xhigh"})
    assert params.reasoning_effort == "xhigh"
    assert params.openai_payload()["reasoning_effort"] == "xhigh"
    assert params.ollama_think() is None
    unknown = SamplingParams(reasoning_effort="ultra")
    assert unknown.ollama_think() is None

    executor = FrontierExecutor(
        base_url="https://generativelanguage.googleapis.com/v1beta/openai",
        default_model="gemini-4-hydrogen",
        api_key="test",
        provider="openai",
    )
    request = InternalRequest(
        messages=[Message(role="user", content="hi")],
        model="daari",
        sampling=SamplingParams(reasoning_effort="xhigh"),
    )
    payload = executor._openai_payload(request, stream=False)
    assert payload["model"] == "gemini-4-hydrogen"
    assert payload["reasoning_effort"] == "xhigh"


def test_signal_override_can_pin_xhigh_and_still_rejects_unknown():
    rule = SignalOverrideRule(id="h", match={"has_images": False}, reasoning_effort="xhigh")
    request = InternalRequest(
        messages=[Message(role="user", content="hi")],
        model="daari",
    )
    _, levers = apply_signal_override(build_prompt_profile(request), request, rule)
    assert levers["reasoning_effort"] == "xhigh"
    assert request.sampling.reasoning_effort == "xhigh"
    with pytest.raises(Exception, match="ultra"):
        SignalOverrideRule(id="bad", match={"has_images": True}, reasoning_effort="ultra")


def test_docs_mention_hydrogen_next_to_carbon_and_argon():
    budgets = BUDGETS.read_text(encoding="utf-8")
    compare = COMPARE.read_text(encoding="utf-8")
    for model in ("gemini-4-carbon", "gemini-4-argon", "gemini-4-hydrogen"):
        assert model in budgets
    assert "Carbon" in compare and "Argon" in compare and "Hydrogen" in compare
    assert "1.8" in budgets
    assert "xhigh" in budgets
    assert "xhigh" in compare
