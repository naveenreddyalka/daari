"""gpt-6.1-terra pricing, capabilities, and param compat (#1963)."""

from __future__ import annotations

from pathlib import Path

import pytest

from daari.config.settings import Settings
from daari.pricing import cost_usd, matching_model_key, resolve_price
from daari.router.capabilities import known_model_capabilities
from daari.router.param_compat import apply_frontier_param_compat, lookup_frontier_param_compat

BUDGETS = Path("docs/developer/guides/configuration/budgets-frontier.md")


def test_gpt_6_1_terra_short_context_rates():
    settings = Settings()
    price = resolve_price("gpt-6.1-terra", settings.pricing, fallback_per_1k=0.002)
    assert price.is_fallback is False
    assert price.input_per_1m == pytest.approx(1.0)
    assert price.output_per_1m == pytest.approx(5.0)
    assert price.cached_input_per_1m == pytest.approx(0.05)
    assert price.cache_write_30m_per_1m == pytest.approx(1.25)
    assert price.cache_write_12h_per_1m == pytest.approx(2.50)
    catalog = settings.pricing.models["gpt-6.1-terra"]
    assert catalog.input_threshold_tokens == 272_000
    assert catalog.above_input_per_1m == pytest.approx(2.0)
    assert catalog.above_output_per_1m == pytest.approx(7.50)


def test_gpt_6_1_terra_above_272k_uses_threshold_rates():
    settings = Settings()
    below = cost_usd(
        "gpt-6.1-terra",
        271_999,
        1000,
        settings.pricing,
        fallback_per_1k=0.002,
    )
    assert below == pytest.approx(271_999 / 1_000_000 * 1.0 + 1000 / 1_000_000 * 5.0)

    above = cost_usd(
        "gpt-6.1-terra",
        272_000,
        1000,
        settings.pricing,
        fallback_per_1k=0.002,
    )
    assert above == pytest.approx(272_000 / 1_000_000 * 2.0 + 1000 / 1_000_000 * 7.50)


def test_gpt_6_1_terra_prefix_keeps_gpt_5_6_terra():
    settings = Settings()
    table = settings.pricing.models
    assert matching_model_key("gpt-6.1-terra", table) == "gpt-6.1-terra"
    assert matching_model_key("openai.gpt-6.1-terra-20261026", table) == "gpt-6.1-terra"
    legacy = resolve_price("gpt-5.6-terra", settings.pricing, fallback_per_1k=0.002)
    assert legacy.input_per_1m == pytest.approx(2.0)
    assert matching_model_key("gpt-6.1-terra", table) != "gpt-5.6-terra"


def test_gpt_6_1_terra_capabilities_and_param_compat():
    caps = known_model_capabilities("gpt-6.1-terra")
    assert {"tools", "json", "vision", "long_context"} <= set(caps)
    entry = lookup_frontier_param_compat("gpt-6.1-terra")
    assert entry is not None
    assert {"temperature", "top_p", "logprobs"} <= set(entry.unsupported_params)
    assert entry.tools_transport == "responses"
    # Terra publishes reasoning.effort=none — do not forbid it.
    assert "none" not in entry.unsupported_reasoning_efforts
    assert lookup_frontier_param_compat("openai.gpt-6.1-terra") is entry


def test_gpt_6_1_terra_chat_tools_warn_toward_responses():
    payload = {
        "model": "gpt-6.1-terra",
        "tools": [{"type": "function", "function": {"name": "f"}}],
        "temperature": 0.2,
    }
    result = apply_frontier_param_compat(payload, "gpt-6.1-terra", has_tools=True)
    assert result.tools_transport_warned is True
    assert any("responses" in w.lower() for w in result.warnings)
    assert "temperature" not in payload


def test_gpt_6_1_terra_reasoning_effort_none_preserved():
    payload = {"model": "gpt-6.1-terra", "reasoning_effort": "none"}
    result = apply_frontier_param_compat(payload, "gpt-6.1-terra", has_tools=False)
    assert payload["reasoning_effort"] == "none"
    assert "reasoning_effort" not in result.dropped_params


def test_budgets_frontier_docs_pin_gpt_6_1_terra():
    text = BUDGETS.read_text(encoding="utf-8")
    assert "gpt-6.1-terra" in text
    assert "gpt-5.6-terra" in text
    assert "1.00" in text or "$1" in text
