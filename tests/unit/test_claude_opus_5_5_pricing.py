"""claude-opus-5-5 pricing, capabilities, and param compat (#1467)."""

from __future__ import annotations

from pathlib import Path

import pytest

from daari.config.settings import Settings
from daari.pricing import cost_usd, matching_model_key, resolve_price
from daari.router.capabilities import anthropic_model_line, known_model_capabilities
from daari.router.param_compat import (
    apply_frontier_param_compat,
    lookup_frontier_param_compat,
)

BUDGETS = Path("docs/developer/guides/configuration/budgets-frontier.md")


def test_claude_opus_5_5_pricing_rates():
    settings = Settings()
    price = resolve_price("claude-opus-5-5", settings.pricing, fallback_per_1k=0.002)
    assert price.is_fallback is False
    assert price.input_per_1m == pytest.approx(4.0)
    assert price.output_per_1m == pytest.approx(20.0)
    assert price.cached_input_per_1m == pytest.approx(0.40)
    assert price.cache_write_1h_per_1m == pytest.approx(8.00)


def test_claude_opus_5_5_does_not_collide_with_opus_5():
    settings = Settings()
    table = settings.pricing.models
    assert matching_model_key("claude-opus-5-5", table) == "claude-opus-5-5"
    assert matching_model_key("claude-opus-5-5-20261003", table) == "claude-opus-5-5"
    assert matching_model_key("anthropic.claude-opus-5-5", table) == "claude-opus-5-5"
    assert matching_model_key("claude-opus-5", table) == "claude-opus-5"
    assert matching_model_key("anthropic.claude-opus-5", table) == "claude-opus-5"


def test_claude_opus_5_5_cache_write_cost():
    settings = Settings()
    usd = cost_usd(
        "claude-opus-5-5",
        input_tokens=0,
        output_tokens=0,
        pricing=settings.pricing,
        fallback_per_1k=0.002,
        cache_write_tokens=1_000_000,
        cache_ttl="1h",
    )
    assert usd == pytest.approx(8.00)


def test_claude_opus_5_5_capabilities_and_line():
    caps = known_model_capabilities("claude-opus-5-5")
    assert {"tools", "json", "vision", "long_context"} <= set(caps)
    assert known_model_capabilities("anthropic.claude-opus-5-5") == caps
    assert anthropic_model_line("claude-opus-5-5") == "opus"
    assert anthropic_model_line("anthropic.claude-opus-5-5-20261003") == "opus"


def test_claude_opus_5_5_param_compat_strips_samplers():
    entry = lookup_frontier_param_compat("claude-opus-5-5")
    assert entry is not None
    assert entry.unsupported_params >= frozenset({"temperature", "top_p", "top_k"})
    assert lookup_frontier_param_compat("anthropic.claude-opus-5-5") is entry

    payload = {
        "model": "claude-opus-5-5",
        "temperature": 0.9,
        "top_p": 0.8,
        "top_k": 40,
        "max_tokens": 1024,
    }
    result = apply_frontier_param_compat(payload, "claude-opus-5-5")
    assert "temperature" not in payload
    assert "top_p" not in payload
    assert "top_k" not in payload
    assert payload["max_tokens"] == 1024
    for name in ("temperature", "top_p", "top_k"):
        assert name in result.dropped_params


def test_claude_opus_5_keeps_samplers_without_compat_entry():
    assert lookup_frontier_param_compat("claude-opus-5") is None
    payload = {"temperature": 0.5, "top_p": 0.9, "top_k": 20}
    result = apply_frontier_param_compat(payload, "claude-opus-5")
    assert payload == {"temperature": 0.5, "top_p": 0.9, "top_k": 20}
    assert result.dropped_params == []


def test_budgets_frontier_docs_pin_claude_opus_5_5():
    text = BUDGETS.read_text(encoding="utf-8")
    assert "claude-opus-5-5" in text
    assert "4.00" in text or "$4" in text or "4.0" in text
