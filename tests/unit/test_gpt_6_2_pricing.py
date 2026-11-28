"""gpt-6.2-astra / gpt-6.2-sol pricing, capabilities, and 12h cache-write (#2367)."""

from __future__ import annotations

from pathlib import Path

import pytest

from daari.config.settings import Settings
from daari.pricing import cost_usd, matching_model_key, resolve_price
from daari.router.capabilities import known_model_capabilities
from daari.router.param_compat import lookup_frontier_param_compat

BUDGETS = Path("docs/developer/guides/configuration/budgets-frontier.md")
COMPARE = Path("docs/developer/resources/compare-litellm.md")


def test_gpt_6_2_astra_short_and_long_context_rates():
    settings = Settings()
    price = resolve_price("gpt-6.2-astra", settings.pricing, fallback_per_1k=0.002)
    assert price.is_fallback is False
    assert price.input_per_1m == pytest.approx(8.0)
    assert price.output_per_1m == pytest.approx(40.0)
    assert price.cached_input_per_1m == pytest.approx(0.40)
    assert price.cache_write_30m_per_1m == pytest.approx(10.0)
    assert price.cache_write_12h_per_1m == pytest.approx(20.0)
    catalog = settings.pricing.models["gpt-6.2-astra"]
    assert catalog.input_threshold_tokens == 272_000
    assert catalog.above_input_per_1m == pytest.approx(16.0)
    assert catalog.above_output_per_1m == pytest.approx(60.0)

    below = cost_usd(
        "gpt-6.2-astra",
        271_999,
        1000,
        settings.pricing,
        fallback_per_1k=0.002,
    )
    assert below == pytest.approx(271_999 / 1_000_000 * 8.0 + 1000 / 1_000_000 * 40.0)

    above = resolve_price(
        "gpt-6.2-astra",
        settings.pricing,
        fallback_per_1k=0.002,
        input_tokens=272_000,
    )
    assert above.input_per_1m == pytest.approx(16.0)
    assert above.output_per_1m == pytest.approx(60.0)
    assert above.cached_input_per_1m == pytest.approx(0.80)
    assert above.cache_write_30m_per_1m == pytest.approx(20.0)
    assert above.cache_write_12h_per_1m == pytest.approx(40.0)


def test_gpt_6_2_sol_short_and_long_context_rates():
    settings = Settings()
    price = resolve_price("gpt-6.2-sol", settings.pricing, fallback_per_1k=0.002)
    assert price.is_fallback is False
    assert price.input_per_1m == pytest.approx(2.0)
    assert price.output_per_1m == pytest.approx(10.0)
    assert price.cached_input_per_1m == pytest.approx(0.10)
    assert price.cache_write_30m_per_1m == pytest.approx(2.50)
    assert price.cache_write_12h_per_1m == pytest.approx(5.0)
    catalog = settings.pricing.models["gpt-6.2-sol"]
    assert catalog.input_threshold_tokens == 272_000
    assert catalog.above_input_per_1m == pytest.approx(4.0)
    assert catalog.above_output_per_1m == pytest.approx(15.0)

    above = resolve_price(
        "gpt-6.2-sol",
        settings.pricing,
        fallback_per_1k=0.002,
        input_tokens=272_000,
    )
    assert above.input_per_1m == pytest.approx(4.0)
    assert above.output_per_1m == pytest.approx(15.0)
    assert above.cached_input_per_1m == pytest.approx(0.20)
    assert above.cache_write_30m_per_1m == pytest.approx(5.0)
    assert above.cache_write_12h_per_1m == pytest.approx(10.0)


@pytest.mark.parametrize(
    "model,write_30m,write_12h",
    [
        ("gpt-6.2-astra", 10.0, 20.0),
        ("gpt-6.2-sol", 2.50, 5.0),
    ],
)
def test_gpt_6_2_twelve_hour_cache_write_billing(
    model: str, write_30m: float, write_12h: float
):
    settings = Settings()
    writes = 1_000_000
    thirty = cost_usd(
        model,
        0,
        0,
        settings.pricing,
        fallback_per_1k=0.002,
        cache_write_tokens=writes,
        cache_ttl="30m",
    )
    twelve = cost_usd(
        model,
        0,
        0,
        settings.pricing,
        fallback_per_1k=0.002,
        cache_write_tokens=writes,
        cache_ttl="12h",
    )
    assert thirty == pytest.approx(write_30m)
    assert twelve == pytest.approx(write_12h)


def test_gpt_6_2_longer_keys_win_over_gpt_6_prefix():
    settings = Settings()
    table = settings.pricing.models
    assert matching_model_key("gpt-6.2-astra", table) == "gpt-6.2-astra"
    assert matching_model_key("openai.gpt-6.2-astra-20261117", table) == "gpt-6.2-astra"
    assert matching_model_key("gpt-6.2-sol", table) == "gpt-6.2-sol"
    assert matching_model_key("openai.gpt-6.2-sol", table) == "gpt-6.2-sol"
    assert matching_model_key("gpt-6.2-astra", table) != "gpt-6-astra"
    assert matching_model_key("gpt-6.2-sol", table) != "gpt-6.1-sol"


def test_gpt_6_2_capabilities_and_param_compat():
    for model in ("gpt-6.2-astra", "gpt-6.2-sol"):
        caps = known_model_capabilities(model)
        assert {"tools", "json", "vision", "audio", "long_context"} <= set(caps)
        entry = lookup_frontier_param_compat(model)
        assert entry is not None
        assert {"temperature", "top_p", "logprobs"} <= set(entry.unsupported_params)
        assert entry.tools_transport == "responses"


def test_budgets_and_compare_docs_mention_gpt_6_2():
    budgets = BUDGETS.read_text(encoding="utf-8")
    assert "gpt-6.2-astra" in budgets
    assert "gpt-6.2-sol" in budgets
    compare = COMPARE.read_text(encoding="utf-8")
    assert "gpt-6.2" in compare or "GPT-6.2" in compare
