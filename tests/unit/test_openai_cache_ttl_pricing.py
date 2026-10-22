"""OpenAI prompt-cache write rates by TTL (30m 1.25× / 12h 2.5×) (#1843)."""

from __future__ import annotations

import pytest

from daari.config.settings import ModelPrice, PricingSettings
from daari.gateway.internal import InternalRequest, Message
from daari.gateway.sampling import SamplingParams
from daari.pricing import cost_usd, resolve_price
from daari.router.anthropic_messages import request_cache_ttl


def test_default_gpt56_models_have_30m_and_12h_write_rates():
    pricing = PricingSettings()
    for model in ("gpt-5.6", "gpt-5.6-sol", "gpt-6-astra", "gpt-6.1-sol"):
        price = resolve_price(model, pricing, fallback_per_1k=0.002)
        assert price.cache_write_30m_per_1m == pytest.approx(price.input_per_1m * 1.25)
        assert price.cache_write_12h_per_1m == pytest.approx(price.input_per_1m * 2.5)


def test_twelve_hour_write_costs_double_thirty_minute():
    """Identical usage: ttl 12h write component is 2× the 30m write component."""
    pricing = PricingSettings(
        models={
            "gpt-5.6": ModelPrice(
                input_per_1m=4.0,
                output_per_1m=20.0,
                cached_input_per_1m=0.40,
                cache_write_30m_per_1m=5.0,
                cache_write_12h_per_1m=10.0,
            )
        }
    )
    writes = 1_000_000
    thirty = cost_usd(
        "gpt-5.6",
        0,
        0,
        pricing,
        fallback_per_1k=0.002,
        cache_write_tokens=writes,
        cache_ttl="30m",
    )
    twelve = cost_usd(
        "gpt-5.6",
        0,
        0,
        pricing,
        fallback_per_1k=0.002,
        cache_write_tokens=writes,
        cache_ttl="12h",
    )
    assert thirty == pytest.approx(5.0)
    assert twelve == pytest.approx(10.0)
    assert twelve == pytest.approx(thirty * 2.0)


def test_request_cache_ttl_from_prompt_cache_options():
    req = InternalRequest(
        messages=[Message(role="user", content="hi")],
        model="daari",
        sampling=SamplingParams(prompt_cache_options={"ttl": "12h"}),
    )
    assert request_cache_ttl(req) == "12h"


def test_request_cache_ttl_defaults_30m_when_options_present_without_ttl():
    req = InternalRequest(
        messages=[Message(role="user", content="hi")],
        model="daari",
        sampling=SamplingParams(prompt_cache_options={}),
    )
    assert request_cache_ttl(req) == "30m"


def test_request_cache_ttl_prefers_longest_breakpoint():
    req = InternalRequest(
        messages=[Message(role="user", content="hi")],
        model="daari",
        sampling=SamplingParams(
            prompt_cache_options={
                "ttl": "30m",
                "breakpoints": [
                    {"type": "prompt_cache_breakpoint", "ttl": "30m"},
                    {"type": "prompt_cache_breakpoint", "ttl": "12h"},
                ],
            }
        ),
    )
    assert request_cache_ttl(req) == "12h"


def test_chargeback_docs_note_openai_ttl_write_rates():
    from pathlib import Path

    text = (
        Path(__file__).resolve().parents[2]
        / "docs/developer/guides/observability/chargeback.md"
    ).read_text(encoding="utf-8")
    assert "30m" in text and "12h" in text
    assert "1.25" in text or "1.25×" in text or "1.25x" in text
    assert "2.5" in text
    assert "prompt_cache_options" in text
