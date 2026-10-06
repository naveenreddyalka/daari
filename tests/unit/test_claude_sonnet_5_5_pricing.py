"""claude-sonnet-5-5 pricing, capabilities, and param compat (#1450)."""

from __future__ import annotations

from pathlib import Path

import pytest

from daari.config.settings import Settings
from daari.pricing import cost_usd, matching_model_key, resolve_price
from daari.router.capabilities import known_model_capabilities
from daari.router.param_compat import (
    apply_frontier_param_compat,
    lookup_frontier_param_compat,
)

BUDGETS = Path("docs/developer/guides/configuration/budgets-frontier.md")


def test_claude_sonnet_5_5_pricing_rates():
    settings = Settings()
    price = resolve_price("claude-sonnet-5-5", settings.pricing, fallback_per_1k=0.002)
    assert price.is_fallback is False
    assert price.input_per_1m == pytest.approx(2.0)
    assert price.output_per_1m == pytest.approx(10.0)
    assert price.cached_input_per_1m == pytest.approx(0.20)
    assert price.cache_write_1h_per_1m == pytest.approx(4.00)


def test_claude_sonnet_5_5_does_not_collide_with_sonnet_5():
    settings = Settings()
    table = settings.pricing.models
    assert matching_model_key("claude-sonnet-5-5", table) == "claude-sonnet-5-5"
    assert matching_model_key("claude-sonnet-5-5-20260928", table) == "claude-sonnet-5-5"
    assert matching_model_key("anthropic.claude-sonnet-5-5", table) == "claude-sonnet-5-5"
    # Sibling keeps its own key (same rates, distinct catalog entry).
    assert matching_model_key("claude-sonnet-5", table) == "claude-sonnet-5"
    assert matching_model_key("anthropic.claude-sonnet-5", table) == "claude-sonnet-5"


def test_claude_sonnet_5_5_cache_write_cost():
    settings = Settings()
    usd = cost_usd(
        "claude-sonnet-5-5",
        input_tokens=0,
        output_tokens=0,
        pricing=settings.pricing,
        fallback_per_1k=0.002,
        cache_write_tokens=1_000_000,
        cache_ttl="1h",
    )
    assert usd == pytest.approx(4.00)


def test_claude_sonnet_5_5_capabilities():
    caps = known_model_capabilities("claude-sonnet-5-5")
    assert {"tools", "json", "vision", "long_context"} <= set(caps)
    assert known_model_capabilities("anthropic.claude-sonnet-5-5") == caps
    assert known_model_capabilities("claude-sonnet-5-5-20260928") == caps


def test_claude_sonnet_5_5_param_compat_strips_samplers():
    entry = lookup_frontier_param_compat("claude-sonnet-5-5")
    assert entry is not None
    assert entry.unsupported_params >= frozenset({"temperature", "top_p", "top_k"})
    assert lookup_frontier_param_compat("anthropic.claude-sonnet-5-5") is entry
    assert lookup_frontier_param_compat("claude-sonnet-5-5-20260928") is entry

    payload = {
        "model": "claude-sonnet-5-5",
        "temperature": 0.9,
        "top_p": 0.8,
        "top_k": 40,
        "max_tokens": 1024,
    }
    result = apply_frontier_param_compat(payload, "claude-sonnet-5-5")
    assert "temperature" not in payload
    assert "top_p" not in payload
    assert "top_k" not in payload
    assert payload["max_tokens"] == 1024
    for name in ("temperature", "top_p", "top_k"):
        assert name in result.dropped_params


def test_claude_sonnet_5_keeps_samplers_without_compat_entry():
    """Sonnet 5 is priced/capable but does not share the 5.5 sampler strip."""
    assert lookup_frontier_param_compat("claude-sonnet-5") is None
    payload = {"temperature": 0.5, "top_p": 0.9, "top_k": 20}
    result = apply_frontier_param_compat(payload, "claude-sonnet-5")
    assert payload == {"temperature": 0.5, "top_p": 0.9, "top_k": 20}
    assert result.dropped_params == []


def test_budgets_frontier_docs_pin_claude_sonnet_5_5():
    text = BUDGETS.read_text(encoding="utf-8")
    assert "claude-sonnet-5-5" in text
    assert "2.00" in text or "$2" in text or "2.0" in text
