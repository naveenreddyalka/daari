"""OpenAI regional-processing 10% uplift when region_pin is set (#1531)."""

from __future__ import annotations

import pytest

from daari.config.settings import Settings
from daari.gateway.cost_headers import COST_HEADER, response_cost_headers
from daari.gateway.internal import DaariMeta
from daari.pricing import cost_usd, regional_processing_factor


@pytest.mark.parametrize("pin", ["us", "eu", "US", " EU "])
def test_regional_factor_is_1_10_for_post_cutoff_openai_models(pin):
    assert regional_processing_factor(pin, "gpt-6-luna") == pytest.approx(1.10)
    assert regional_processing_factor(pin, "gpt-6-astra") == pytest.approx(1.10)
    assert regional_processing_factor(pin, "gpt-6.1-sol") == pytest.approx(1.10)
    assert regional_processing_factor(pin, "gpt-5.6") == pytest.approx(1.10)


def test_regional_factor_is_1_without_pin_or_pre_cutoff_model():
    assert regional_processing_factor(None, "gpt-6-luna") == 1.0
    assert regional_processing_factor("", "gpt-6-luna") == 1.0
    assert regional_processing_factor("us", "gpt-4o-mini") == 1.0
    assert regional_processing_factor("eu", "claude-sonnet-5-5") == 1.0
    assert regional_processing_factor("apac", "gpt-6-luna") == 1.0


def test_chat_cost_uplift_with_region_pin():
    settings = Settings()
    base = cost_usd(
        "gpt-6-luna",
        1_000_000,
        1_000_000,
        settings.pricing,
        fallback_per_1k=0.002,
    )
    pinned = cost_usd(
        "gpt-6-luna",
        1_000_000,
        1_000_000,
        settings.pricing,
        fallback_per_1k=0.002,
        region_pin="us",
    )
    assert base == pytest.approx(0.60)
    assert pinned == pytest.approx(base * 1.10)


def test_no_uplift_when_region_pin_unset():
    settings = Settings()
    # Stay under gpt-6-astra's 272K threshold so the short-context rate applies.
    assert cost_usd(
        "gpt-6-astra",
        100_000,
        0,
        settings.pricing,
        fallback_per_1k=0.002,
        region_pin=None,
    ) == pytest.approx(1.0)


def test_uplift_stacks_with_fast_service_tier():
    """Regional premium multiplies the Fast/Ultrafast rate, not instead of it."""
    settings = Settings()
    standard = cost_usd(
        "gpt-6.1-sol",
        1_000_000,
        0,
        settings.pricing,
        fallback_per_1k=0.002,
    )
    fast = cost_usd(
        "gpt-6.1-sol",
        1_000_000,
        0,
        settings.pricing,
        fallback_per_1k=0.002,
        service_tier="fast",
    )
    fast_regional = cost_usd(
        "gpt-6.1-sol",
        1_000_000,
        0,
        settings.pricing,
        fallback_per_1k=0.002,
        service_tier="fast",
        region_pin="eu",
    )
    assert fast == pytest.approx(standard * 2.0)
    assert fast_regional == pytest.approx(standard * 2.0 * 1.10)


def test_responses_path_cost_header_uses_region_pin():
    settings = Settings()
    meta = DaariMeta(
        tier="L6",
        executor="frontier",
        model="gpt-6-astra",
        input_tokens=100_000,
        output_tokens=0,
        region_pin="us",
    )
    headers = response_cost_headers(meta, settings)
    assert float(headers[COST_HEADER]) == pytest.approx(1.10)


def test_decisions_input_only_path_applies_uplift():
    settings = Settings()
    base = cost_usd(
        "gpt-6-luna",
        1_000_000,
        1_000_000,
        settings.pricing,
        fallback_per_1k=0.002,
        billing_path="decisions",
    )
    pinned = cost_usd(
        "gpt-6-luna",
        1_000_000,
        1_000_000,
        settings.pricing,
        fallback_per_1k=0.002,
        billing_path="decisions",
        region_pin="eu",
    )
    assert base == pytest.approx(0.10)
    assert pinned == pytest.approx(0.11)
