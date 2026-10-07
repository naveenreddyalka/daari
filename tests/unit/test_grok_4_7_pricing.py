"""grok-4.7 pricing, capabilities, and param compat (#1466)."""

from __future__ import annotations

from pathlib import Path

import pytest

from daari.config.settings import Settings
from daari.pricing import matching_model_key, resolve_price
from daari.router.capabilities import known_model_capabilities
from daari.router.param_compat import apply_frontier_param_compat, lookup_frontier_param_compat

BUDGETS = Path("docs/developer/guides/configuration/budgets-frontier.md")


def test_grok_4_7_pricing_rates():
    settings = Settings()
    price = resolve_price("grok-4.7", settings.pricing, fallback_per_1k=0.002)
    assert price.is_fallback is False
    assert price.input_per_1m == pytest.approx(2.0)
    assert price.output_per_1m == pytest.approx(6.0)
    assert price.cached_input_per_1m == pytest.approx(0.50)


def test_grok_4_7_vendor_prefixed_forms():
    settings = Settings()
    table = settings.pricing.models
    assert matching_model_key("grok-4.7", table) == "grok-4.7"
    assert matching_model_key("xai.grok-4.7", table) == "grok-4.7"
    assert matching_model_key("xai/grok-4.7", table) == "grok-4.7"
    assert matching_model_key("openrouter/x-ai/grok-4.7", table) == "grok-4.7"
    assert matching_model_key("grok-4.7-20261004", table) == "grok-4.7"


def test_grok_4_7_capabilities():
    caps = known_model_capabilities("grok-4.7")
    assert {"tools", "json", "vision", "long_context"} <= set(caps)
    assert known_model_capabilities("xai.grok-4.7") == caps
    assert known_model_capabilities("xai/grok-4.7") == caps


def test_grok_4_7_param_compat_no_sampler_strip():
    """No published sampler → 400 rule for Grok 4.7; leave knobs alone."""
    assert lookup_frontier_param_compat("grok-4.7") is None
    payload = {"temperature": 0.7, "top_p": 0.9, "max_tokens": 256}
    result = apply_frontier_param_compat(payload, "grok-4.7")
    assert payload == {"temperature": 0.7, "top_p": 0.9, "max_tokens": 256}
    assert result.dropped_params == []


def test_budgets_frontier_docs_pin_grok_4_7():
    text = BUDGETS.read_text(encoding="utf-8")
    assert "grok-4.7" in text
    assert "2.00" in text or "$2" in text or "2.0" in text
