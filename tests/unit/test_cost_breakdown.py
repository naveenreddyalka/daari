"""Kong AI Gateway 2.3.0 parity: input/output cost split (#2182)."""

from __future__ import annotations

import pytest
from types import SimpleNamespace

from daari.config.settings import ModelPrice, PricingSettings, Settings
from daari.gateway.cost_headers import (
    COST_HEADER,
    COST_INPUT_HEADER,
    COST_OUTPUT_HEADER,
    StreamOutcome,
    response_cost_headers,
    stream_usage_cost_breakdown,
)
from daari.gateway.internal import DaariMeta
from daari.pricing import cost_breakdown, cost_usd


def _pricing() -> PricingSettings:
    return PricingSettings(
        models={
            "claude-sonnet-5": ModelPrice(
                input_per_1m=3.0,
                output_per_1m=15.0,
                cached_input_per_1m=0.30,
                cache_write_1h_per_1m=3.75,
                cache_write_30m_per_1m=3.75,
                cache_write_12h_per_1m=7.50,
            )
        }
    )


def test_breakdown_sums_to_cost_usd_with_cache_writes_tier_region_speed():
    pricing = _pricing()
    kwargs = dict(
        model="claude-sonnet-5",
        input_tokens=1_000_000,
        output_tokens=500_000,
        pricing=pricing,
        fallback_per_1k=0.002,
        cached_input_tokens=200_000,
        cache_write_tokens=100_000,
        cache_ttl="1h",
        service_tier="priority",
        region_pin=None,
        usage_speed="fast",
    )
    parts = cost_breakdown(**kwargs)
    total = cost_usd(**kwargs)
    assert parts.input_usd + parts.output_usd == pytest.approx(total)
    assert parts.input_usd > 0
    assert parts.output_usd > 0
    # Input side includes billable + cached-read + cache-write (all > 0 here).
    bare_out = cost_breakdown(
        "claude-sonnet-5",
        0,
        500_000,
        pricing,
        fallback_per_1k=0.002,
        service_tier="priority",
        usage_speed="fast",
    )
    assert parts.output_usd == pytest.approx(bare_out.output_usd)


def test_breakdown_applies_region_pin_to_both_sides():
    settings = Settings()
    kwargs = dict(
        model="gpt-6-luna",
        input_tokens=1_000_000,
        output_tokens=1_000_000,
        pricing=settings.pricing,
        fallback_per_1k=0.002,
        region_pin="us",
    )
    parts = cost_breakdown(**kwargs)
    total = cost_usd(**kwargs)
    unpinned = cost_breakdown(
        "gpt-6-luna",
        1_000_000,
        1_000_000,
        settings.pricing,
        fallback_per_1k=0.002,
    )
    assert parts.input_usd + parts.output_usd == pytest.approx(total)
    assert parts.input_usd == pytest.approx(unpinned.input_usd * 1.10)
    assert parts.output_usd == pytest.approx(unpinned.output_usd * 1.10)


def test_response_cost_headers_emit_input_output_split():
    settings = Settings.model_validate(
        {
            "usage": {"frontier_price_per_1k_tokens": 0.002},
            "pricing": {
                "models": {
                    "claude-sonnet-5": {
                        "input_per_1m": 3.0,
                        "output_per_1m": 15.0,
                        "cached_input_per_1m": 0.30,
                        "cache_write_1h_per_1m": 3.75,
                    }
                }
            },
        }
    )
    meta = DaariMeta(
        tier="L6",
        executor="frontier",
        model="claude-sonnet-5",
        input_tokens=1_000_000,
        output_tokens=500_000,
        cached_tokens=200_000,
        cache_write_tokens=100_000,
        service_tier="priority",
        usage_speed="fast",
    )
    headers = response_cost_headers(meta, settings)
    parts = cost_breakdown(
        "claude-sonnet-5",
        1_000_000,
        500_000,
        settings.pricing,
        fallback_per_1k=0.002,
        cached_input_tokens=200_000,
        cache_write_tokens=100_000,
        service_tier="priority",
        usage_speed="fast",
    )
    assert float(headers[COST_HEADER]) == pytest.approx(parts.input_usd + parts.output_usd)
    assert float(headers[COST_INPUT_HEADER]) == pytest.approx(parts.input_usd)
    assert float(headers[COST_OUTPUT_HEADER]) == pytest.approx(parts.output_usd)


def test_local_tier_reports_zero_input_and_output_cost():
    meta = DaariMeta(tier="L3", executor="ollama", model="llama3.2:3b")
    headers = response_cost_headers(
        meta, Settings(), prompt_chars=4000, completion_chars=4000
    )
    assert float(headers[COST_HEADER]) == 0.0
    assert float(headers[COST_INPUT_HEADER]) == 0.0
    assert float(headers[COST_OUTPUT_HEADER]) == 0.0


def test_stream_outcome_emits_cost_split_headers():
    outcome = StreamOutcome().note("L6")
    outcome.response_cost = "0.12"
    outcome.response_cost_input = "0.04"
    outcome.response_cost_output = "0.08"
    headers = outcome.headers()
    assert headers[COST_HEADER] == "0.12"
    assert headers[COST_INPUT_HEADER] == "0.04"
    assert headers[COST_OUTPUT_HEADER] == "0.08"


def test_stream_usage_cost_breakdown_matches_cost_breakdown():
    pricing = SimpleNamespace(
        models={
            "claude-sonnet": SimpleNamespace(
                input_per_1m=3.0,
                output_per_1m=15.0,
                cached_input_per_1m=0.30,
                cache_write_1h_per_1m=3.75,
            )
        }
    )
    parts = stream_usage_cost_breakdown(
        tier="L6",
        model="claude-sonnet",
        prompt_tokens=1000,
        completion_tokens=200,
        pricing=pricing,
        fallback_per_1k=0.002,
        cached_input_tokens=100,
        cache_write_tokens=50,
        cache_ttl="1h",
        service_tier="priority",
        usage_speed="fast",
    )
    expected = cost_breakdown(
        "claude-sonnet",
        1000,
        200,
        pricing,
        fallback_per_1k=0.002,
        cached_input_tokens=100,
        cache_write_tokens=50,
        cache_ttl="1h",
        service_tier="priority",
        usage_speed="fast",
    )
    assert parts.input_usd == pytest.approx(expected.input_usd)
    assert parts.output_usd == pytest.approx(expected.output_usd)
    assert parts.input_usd + parts.output_usd == pytest.approx(
        expected.input_usd + expected.output_usd
    )
    local = stream_usage_cost_breakdown(
        tier="L3", model="llama", prompt_tokens=1000, completion_tokens=200
    )
    assert local.input_usd == 0.0
    assert local.output_usd == 0.0
