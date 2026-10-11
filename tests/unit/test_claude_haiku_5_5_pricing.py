"""claude-haiku-5-5 pricing, capabilities, and param compat (#1505)."""

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


def test_claude_haiku_5_5_pricing_rates_below_threshold():
    settings = Settings()
    price = resolve_price("claude-haiku-5-5", settings.pricing, fallback_per_1k=0.002)
    assert price.is_fallback is False
    assert price.input_per_1m == pytest.approx(0.10)
    assert price.output_per_1m == pytest.approx(0.50)
    assert price.cached_input_per_1m == pytest.approx(0.01)
    assert price.cache_write_per_1m == pytest.approx(0.125)
    assert price.cache_write_1h_per_1m == pytest.approx(0.20)
    assert price.input_threshold_tokens == 100_000


def test_claude_haiku_5_5_threshold_scales_cache_and_1h_write():
    settings = Settings()
    price = settings.pricing.models["claude-haiku-5-5"]
    assert price.input_threshold_tokens == 100_000
    assert price.above_input_per_1m == pytest.approx(0.50)
    assert price.above_output_per_1m == pytest.approx(2.50)

    below = resolve_price(
        "claude-haiku-5-5",
        settings.pricing,
        fallback_per_1k=0.002,
        input_tokens=99_999,
    )
    assert below.cached_input_per_1m == pytest.approx(0.01)
    assert below.cache_write_per_1m == pytest.approx(0.125)
    assert below.cache_write_1h_per_1m == pytest.approx(0.20)

    above = resolve_price(
        "claude-haiku-5-5",
        settings.pricing,
        fallback_per_1k=0.002,
        input_tokens=100_000,
    )
    assert above.input_per_1m == pytest.approx(0.50)
    assert above.output_per_1m == pytest.approx(2.50)
    assert above.cached_input_per_1m == pytest.approx(0.05)
    assert above.cache_write_per_1m == pytest.approx(0.625)
    assert above.cache_write_1h_per_1m == pytest.approx(1.00)

    cache_usd = cost_usd(
        "claude-haiku-5-5",
        input_tokens=100_000,
        output_tokens=0,
        pricing=settings.pricing,
        fallback_per_1k=0.002,
        cached_input_tokens=1_000_000,
    )
    # Billable input is max(0, 100k - 1M) = 0; cache read at above rate.
    assert cache_usd == pytest.approx(0.05)

    write_usd = cost_usd(
        "claude-haiku-5-5",
        input_tokens=100_000,
        output_tokens=0,
        pricing=settings.pricing,
        fallback_per_1k=0.002,
        cache_write_tokens=1_000_000,
        cache_ttl="1h",
    )
    assert write_usd == pytest.approx(100_000 / 1_000_000 * 0.50 + 1.00)


def test_claude_haiku_5_5_does_not_collide_with_haiku_4_5():
    settings = Settings()
    table = settings.pricing.models
    assert matching_model_key("claude-haiku-5-5", table) == "claude-haiku-5-5"
    assert matching_model_key("claude-haiku-5-5-20261007", table) == "claude-haiku-5-5"
    assert matching_model_key("anthropic.claude-haiku-5-5", table) == "claude-haiku-5-5"
    assert matching_model_key("claude-haiku-4-5", table) == "claude-haiku-4-5"
    assert matching_model_key("anthropic.claude-haiku-4-5", table) == "claude-haiku-4-5"


def test_claude_sonnet_and_opus_5_5_cache_reads_halved():
    settings = Settings()
    sonnet = resolve_price("claude-sonnet-5-5", settings.pricing, fallback_per_1k=0.002)
    opus = resolve_price("claude-opus-5-5", settings.pricing, fallback_per_1k=0.002)
    assert sonnet.cached_input_per_1m == pytest.approx(0.10)
    assert opus.cached_input_per_1m == pytest.approx(0.20)


def test_claude_haiku_5_5_capabilities_and_line():
    caps = known_model_capabilities("claude-haiku-5-5")
    assert {"tools", "json", "vision", "long_context"} <= set(caps)
    assert known_model_capabilities("anthropic.claude-haiku-5-5") == caps
    assert known_model_capabilities("claude-haiku-5-5-20261007") == caps
    assert anthropic_model_line("claude-haiku-5-5") == "haiku"
    assert anthropic_model_line("anthropic.claude-haiku-5-5-20261007") == "haiku"


def test_claude_haiku_5_5_param_compat_strips_samplers():
    entry = lookup_frontier_param_compat("claude-haiku-5-5")
    assert entry is not None
    assert entry.unsupported_params >= frozenset({"temperature", "top_p", "top_k"})
    assert lookup_frontier_param_compat("anthropic.claude-haiku-5-5") is entry
    assert lookup_frontier_param_compat("claude-haiku-5-5-20261007") is entry

    payload = {
        "model": "claude-haiku-5-5",
        "temperature": 0.9,
        "top_p": 0.8,
        "top_k": 40,
        "max_tokens": 1024,
    }
    result = apply_frontier_param_compat(payload, "claude-haiku-5-5")
    assert "temperature" not in payload
    assert "top_p" not in payload
    assert "top_k" not in payload
    assert payload["max_tokens"] == 1024
    for name in ("temperature", "top_p", "top_k"):
        assert name in result.dropped_params


def test_claude_haiku_4_5_keeps_samplers_without_compat_entry():
    assert lookup_frontier_param_compat("claude-haiku-4-5") is None
    payload = {"temperature": 0.5, "top_p": 0.9, "top_k": 20}
    result = apply_frontier_param_compat(payload, "claude-haiku-4-5")
    assert payload == {"temperature": 0.5, "top_p": 0.9, "top_k": 20}
    assert result.dropped_params == []


def test_claude_haiku_5_5_five_minute_cache_write_rates():
    """5m cache writes bill $0.125/MTok below 100K and $0.625 above (#1520)."""
    settings = Settings()
    below = cost_usd(
        "claude-haiku-5-5",
        input_tokens=99_999,
        output_tokens=0,
        pricing=settings.pricing,
        fallback_per_1k=0.002,
        cache_write_tokens=1_000_000,
        cache_ttl="5m",
    )
    assert below == pytest.approx(99_999 / 1_000_000 * 0.10 + 0.125)

    above = cost_usd(
        "claude-haiku-5-5",
        input_tokens=100_000,
        output_tokens=0,
        pricing=settings.pricing,
        fallback_per_1k=0.002,
        cache_write_tokens=1_000_000,
        cache_ttl="5m",
    )
    assert above == pytest.approx(100_000 / 1_000_000 * 0.50 + 0.625)


def test_claude_haiku_5_5_maps_budget_tokens_to_adaptive():
    """Manual budget_tokens must never reach Anthropic egress for haiku-5-5 (#1520)."""
    from daari.gateway.internal import InternalRequest, Message
    from daari.gateway.sampling import SamplingParams
    from daari.router.anthropic_messages import to_anthropic_payload

    request = InternalRequest(
        messages=[Message(role="user", content="hi")],
        model="claude-haiku-5-5",
        sampling=SamplingParams(
            max_tokens=1024,
            thinking={"type": "enabled", "budget_tokens": 4096},
        ),
    )
    payload = to_anthropic_payload(request, model="claude-haiku-5-5")
    result = apply_frontier_param_compat(payload, "claude-haiku-5-5")
    assert "budget_tokens" not in (payload.get("thinking") or {})
    assert payload["thinking"] == {"type": "adaptive"}
    assert payload["output_config"]["effort"] == "medium"
    assert any("budget_tokens" in w for w in result.warnings)
    assert "budget_tokens" in result.dropped_params


def test_claude_haiku_5_5_model_card_limits_and_adaptive_default():
    from daari.router.capabilities import anthropic_capabilities, anthropic_model_limits

    limits = anthropic_model_limits("claude-haiku-5-5")
    assert limits["context_window"] == 1_000_000
    assert limits["max_output_tokens"] == 128_000
    caps = anthropic_capabilities("claude-haiku-5-5")
    assert caps["thinking"]["types"]["adaptive"]["supported"] is True
    assert caps["thinking"]["types"]["adaptive"]["default"] is True
    assert caps["thinking"]["default_effort"] == "medium"


def test_budgets_frontier_docs_pin_claude_haiku_5_5():
    text = BUDGETS.read_text(encoding="utf-8")
    assert "claude-haiku-5-5" in text
    assert "0.10" in text or "$0.10" in text
