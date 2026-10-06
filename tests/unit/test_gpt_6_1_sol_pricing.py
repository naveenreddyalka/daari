"""gpt-6.1-sol pricing, capabilities, and param compat (#1442)."""

from __future__ import annotations

from pathlib import Path

import pytest

from daari.config.settings import Settings
from daari.pricing import cost_usd, matching_model_key, pricing_warnings, resolve_price
from daari.router.capabilities import known_model_capabilities
from daari.router.param_compat import lookup_frontier_param_compat

BUDGETS = Path("docs/developer/guides/configuration/budgets-frontier.md")


def test_gpt_6_1_sol_pricing_rates():
    settings = Settings()
    price = resolve_price("gpt-6.1-sol", settings.pricing, fallback_per_1k=0.002)
    assert price.is_fallback is False
    assert price.input_per_1m == pytest.approx(2.0)
    assert price.output_per_1m == pytest.approx(10.0)
    assert price.cached_input_per_1m == pytest.approx(0.10)
    assert price.cache_write_1h_per_1m == pytest.approx(2.50)
    # No invented long-context surcharge.
    assert price.input_threshold_tokens is None


def test_gpt_6_1_sol_prefix_does_not_collide_with_astra_or_gpt56():
    settings = Settings()
    table = settings.pricing.models
    assert matching_model_key("gpt-6.1-sol", table) == "gpt-6.1-sol"
    assert matching_model_key("gpt-6.1-sol-20260929", table) == "gpt-6.1-sol"
    assert matching_model_key("openai.gpt-6.1-sol", table) == "gpt-6.1-sol"
    # Sibling ids keep their own rates.
    astra = resolve_price("gpt-6-astra", settings.pricing, fallback_per_1k=0.002)
    assert astra.input_per_1m == pytest.approx(10.0)
    sol56 = resolve_price("gpt-5.6-sol", settings.pricing, fallback_per_1k=0.002)
    assert sol56.input_per_1m == pytest.approx(4.0)
    # gpt-6.1-sol must not resolve as astra or gpt-5.6*.
    key = matching_model_key("gpt-6.1-sol", table)
    assert key not in {"gpt-6-astra", "gpt-5.6", "gpt-5.6-sol"}


def test_gpt_6_1_sol_cache_write_cost():
    settings = Settings()
    usd = cost_usd(
        "gpt-6.1-sol",
        input_tokens=0,
        output_tokens=0,
        pricing=settings.pricing,
        fallback_per_1k=0.002,
        cache_write_tokens=1_000_000,
        cache_ttl="1h",
    )
    assert usd == pytest.approx(2.50)


def test_gpt_6_1_sol_capabilities_and_param_compat():
    caps = known_model_capabilities("gpt-6.1-sol")
    assert {"tools", "json", "vision", "long_context"} <= set(caps)
    entry = lookup_frontier_param_compat("gpt-6.1-sol")
    assert entry is not None
    assert "temperature" in entry.unsupported_params
    assert entry.tools_transport == "responses"
    assert lookup_frontier_param_compat("openai.gpt-6.1-sol-20260929") is entry


def test_doctor_quiet_when_frontier_is_gpt_6_1_sol():
    settings = Settings()
    settings.frontier.enabled = True
    settings.frontier.model = "gpt-6.1-sol"
    assert pricing_warnings(settings) == []


def test_budgets_frontier_docs_pin_gpt_6_1_sol():
    text = BUDGETS.read_text(encoding="utf-8")
    assert "gpt-6.1-sol" in text
    assert "2.00" in text or "$2" in text or "2.0" in text
