"""Context-threshold pricing for long-context frontier models (issue #411)."""

from __future__ import annotations

import pytest

from daari.config.settings import ModelPrice, Settings
from daari.gateway.cost_headers import COST_HEADER, response_cost_headers
from daari.gateway.internal import DaariMeta
from daari.pricing import cost_usd, resolve_price


def test_below_threshold_matches_flat_rates():
    settings = Settings()
    below = cost_usd(
        "gpt-6-astra",
        271_999,
        1000,
        settings.pricing,
        fallback_per_1k=0.002,
    )
    flat = (
        271_999 / 1_000_000 * 10.0
        + 1000 / 1_000_000 * 50.0
    )
    assert below == pytest.approx(flat)


def test_at_and_above_threshold_uses_2x_input_1_5x_output():
    settings = Settings()
    price = settings.pricing.models["gpt-6-astra"]
    assert price.input_threshold_tokens == 272_000
    assert price.above_input_per_1m == pytest.approx(20.0)
    assert price.above_output_per_1m == pytest.approx(75.0)

    above = cost_usd(
        "gpt-6-astra",
        272_000,
        1000,
        settings.pricing,
        fallback_per_1k=0.002,
    )
    expected = 272_000 / 1_000_000 * 20.0 + 1000 / 1_000_000 * 75.0
    assert above == pytest.approx(expected)

    far = cost_usd(
        "gpt-6-astra",
        400_000,
        2000,
        settings.pricing,
        fallback_per_1k=0.002,
    )
    assert far == pytest.approx(400_000 / 1_000_000 * 20.0 + 2000 / 1_000_000 * 75.0)


def test_models_without_threshold_unchanged():
    settings = Settings()
    assert settings.pricing.models["gpt-4o-mini"].input_threshold_tokens is None
    cost = cost_usd(
        "gpt-4o-mini",
        500_000,
        1000,
        settings.pricing,
        fallback_per_1k=0.002,
    )
    assert cost == pytest.approx(500_000 / 1_000_000 * 0.15 + 1000 / 1_000_000 * 0.60)


def test_config_override_can_set_threshold_fields():
    settings = Settings.model_validate(
        {
            "pricing": {
                "models": {
                    "custom-long": {
                        "input_per_1m": 1.0,
                        "output_per_1m": 2.0,
                        "input_threshold_tokens": 1000,
                        "above_input_per_1m": 3.0,
                        "above_output_per_1m": 4.0,
                    }
                }
            }
        }
    )
    # Overrides replace the whole default table via Field default_factory merge?
    # Settings replaces models dict when provided — ensure our model is there.
    assert "custom-long" in settings.pricing.models
    assert cost_usd(
        "custom-long", 999, 10, settings.pricing, fallback_per_1k=0.002
    ) == pytest.approx(999 / 1_000_000 * 1.0 + 10 / 1_000_000 * 2.0)
    assert cost_usd(
        "custom-long", 1000, 10, settings.pricing, fallback_per_1k=0.002
    ) == pytest.approx(1000 / 1_000_000 * 3.0 + 10 / 1_000_000 * 4.0)


def test_resolve_price_selects_above_tier_by_input_tokens():
    price = ModelPrice(
        input_per_1m=10.0,
        output_per_1m=50.0,
        input_threshold_tokens=272_000,
        above_input_per_1m=20.0,
        above_output_per_1m=75.0,
    )
    settings = Settings.model_validate({"pricing": {"models": {"m": price}}})
    below = resolve_price("m", settings.pricing, fallback_per_1k=0.002, input_tokens=100)
    above = resolve_price("m", settings.pricing, fallback_per_1k=0.002, input_tokens=272_000)
    assert below.input_per_1m == 10.0
    assert above.input_per_1m == 20.0
    assert above.output_per_1m == 75.0


def test_cost_header_uses_threshold_rate():
    settings = Settings()
    meta = DaariMeta(
        tier="L6",
        executor="frontier",
        model="gpt-6-astra",
        input_tokens=272_000,
        output_tokens=0,
    )
    headers = response_cost_headers(meta, settings)
    assert float(headers[COST_HEADER]) == pytest.approx(272_000 / 1_000_000 * 20.0)
