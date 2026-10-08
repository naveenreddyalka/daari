"""gpt-6-luna chat rates stay distinct from Decisions input-only billing (#1484)."""

from __future__ import annotations

from pathlib import Path

import pytest

from daari.config.settings import Settings
from daari.pricing import cost_usd, resolve_price


def test_chat_gpt_6_luna_keeps_output_rate():
    settings = Settings()
    price = resolve_price("gpt-6-luna", settings.pricing, fallback_per_1k=0.002)
    assert price.output_per_1m == pytest.approx(0.50)
    assert price.input_per_1m == pytest.approx(0.10)
    chat = cost_usd(
        "gpt-6-luna",
        input_tokens=1_000_000,
        output_tokens=1_000_000,
        pricing=settings.pricing,
        fallback_per_1k=0.002,
        cached_input_tokens=100_000,
        cache_write_tokens=50_000,
    )
    # 900k input @ $0.10 + 100k cache @ input + 1M output @ $0.50 + 50k write @ input.
    assert chat == pytest.approx(0.605)


def test_decisions_path_gpt_6_luna_is_input_only():
    settings = Settings()
    price = resolve_price(
        "gpt-6-luna",
        settings.pricing,
        fallback_per_1k=0.002,
        billing_path="decisions",
    )
    assert price.input_per_1m == pytest.approx(0.10)
    assert price.output_per_1m == pytest.approx(0.0)
    assert price.cached_input_per_1m == pytest.approx(0.0)
    decisions = cost_usd(
        "gpt-6-luna",
        input_tokens=1_000_000,
        output_tokens=1_000_000,
        pricing=settings.pricing,
        fallback_per_1k=0.002,
        cached_input_tokens=100_000,
        cache_write_tokens=50_000,
        cache_ttl="1h",
        billing_path="decisions",
    )
    # Cache read/write and output are $0; only the uncached 900k input bills.
    assert decisions == pytest.approx(0.09)


def test_decisions_rates_do_not_apply_without_billing_path():
    settings = Settings()
    chat = cost_usd(
        "gpt-6-luna",
        input_tokens=1_000_000,
        output_tokens=2_000_000,
        pricing=settings.pricing,
        fallback_per_1k=0.002,
    )
    decisions = cost_usd(
        "gpt-6-luna",
        input_tokens=1_000_000,
        output_tokens=2_000_000,
        pricing=settings.pricing,
        fallback_per_1k=0.002,
        billing_path="decisions",
    )
    assert chat == pytest.approx(1.10)
    assert decisions == pytest.approx(0.10)
    assert chat != decisions


def test_budgets_guide_pins_chat_and_decisions_luna_rates():
    text = Path("docs/developer/guides/configuration/budgets-frontier.md").read_text(
        encoding="utf-8"
    )
    assert "`gpt-6-luna`" in text
    assert "POST /v1/decisions" in text
    assert "$0 out" in text
