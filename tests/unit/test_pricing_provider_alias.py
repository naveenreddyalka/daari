"""Optional pricing_provider / alias_of catalog aliases (#2005)."""

from __future__ import annotations

import pytest

from daari.config.settings import ModelPrice, Settings
from daari.gateway.cost_headers import COST_HEADER, response_cost_headers
from daari.gateway.internal import DaariMeta
from daari.pricing import cost_usd, pricing_warnings, resolve_price


def test_alias_of_resolves_shipped_catalog_rates():
    settings = Settings()
    settings.pricing.models["openrouter/gpt-4o"] = ModelPrice(alias_of="gpt-4o")
    catalog = settings.pricing.models["gpt-4o"]
    resolved = resolve_price(
        "openrouter/gpt-4o", settings.pricing, fallback_per_1k=0.002
    )
    assert resolved.is_fallback is False
    assert resolved.input_per_1m == pytest.approx(catalog.input_per_1m)
    assert resolved.output_per_1m == pytest.approx(catalog.output_per_1m)
    assert resolved.cached_input_per_1m == pytest.approx(catalog.cached_input_per_1m)


def test_pricing_provider_is_alias_of_synonym():
    settings = Settings()
    settings.pricing.models["azure-gpt-4o-mini"] = ModelPrice(
        pricing_provider="gpt-4o-mini"
    )
    catalog = settings.pricing.models["gpt-4o-mini"]
    resolved = resolve_price(
        "azure-gpt-4o-mini", settings.pricing, fallback_per_1k=0.002
    )
    assert resolved.input_per_1m == pytest.approx(catalog.input_per_1m)
    assert resolved.output_per_1m == pytest.approx(catalog.output_per_1m)


def test_explicit_fields_override_aliased_catalog():
    settings = Settings()
    settings.pricing.models["local-gpt-4o"] = ModelPrice(
        alias_of="gpt-4o",
        output_per_1m=1.0,
    )
    catalog = settings.pricing.models["gpt-4o"]
    resolved = resolve_price("local-gpt-4o", settings.pricing, fallback_per_1k=0.002)
    assert resolved.input_per_1m == pytest.approx(catalog.input_per_1m)
    assert resolved.output_per_1m == pytest.approx(1.0)
    assert cost_usd(
        "local-gpt-4o",
        1_000_000,
        1_000_000,
        settings.pricing,
        fallback_per_1k=0.002,
    ) == pytest.approx(catalog.input_per_1m + 1.0)


def test_unknown_alias_warns_and_falls_back_without_rates():
    settings = Settings()
    settings.frontier.enabled = True
    settings.frontier.model = "mystery-alias"
    settings.pricing.models["mystery-alias"] = ModelPrice(alias_of="does-not-exist")
    warnings = pricing_warnings(settings)
    assert any(
        "mystery-alias" in w and "does-not-exist" in w for w in warnings
    ), warnings
    resolved = resolve_price("mystery-alias", settings.pricing, fallback_per_1k=0.002)
    assert resolved.is_fallback is True
    assert resolved.input_per_1m == pytest.approx(2.0)


def test_alias_longest_key_match_same_as_today():
    settings = Settings()
    # Alias target "gpt-5.6-luna" must resolve the longer catalog key, not Sol.
    settings.pricing.models["vendor/gpt-5.6-luna"] = ModelPrice(alias_of="gpt-5.6-luna")
    catalog = settings.pricing.models["gpt-5.6-luna"]
    sol = settings.pricing.models["gpt-5.6"]
    resolved = resolve_price(
        "vendor/gpt-5.6-luna", settings.pricing, fallback_per_1k=0.002
    )
    assert resolved.input_per_1m == pytest.approx(catalog.input_per_1m)
    assert resolved.input_per_1m != pytest.approx(sol.input_per_1m)


def test_cost_header_uses_aliased_rates():
    settings = Settings()
    settings.pricing.models["or/gpt-4o-mini"] = ModelPrice(alias_of="gpt-4o-mini")
    meta = DaariMeta(
        tier="L6",
        executor="frontier",
        model="or/gpt-4o-mini",
        input_tokens=1_000_000,
        output_tokens=1_000_000,
    )
    headers = response_cost_headers(meta, settings)
    expected = cost_usd(
        "or/gpt-4o-mini",
        1_000_000,
        1_000_000,
        settings.pricing,
        fallback_per_1k=settings.usage.frontier_price_per_1k_tokens,
    )
    assert expected > 0
    assert float(headers[COST_HEADER]) == pytest.approx(expected)


def test_model_price_requires_rates_or_alias():
    with pytest.raises(Exception):
        ModelPrice()
    with pytest.raises(Exception):
        ModelPrice(input_per_1m=1.0)
    assert ModelPrice(alias_of="gpt-4o").alias_of == "gpt-4o"
    assert ModelPrice(input_per_1m=1.0, output_per_1m=2.0).input_per_1m == 1.0
