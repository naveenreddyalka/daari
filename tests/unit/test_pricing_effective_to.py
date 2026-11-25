"""Time-bounded catalog rates: effective_to + baseline fallback (#2297)."""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from daari.config.settings import ModelPrice, ModelPriceBaseline, PricingSettings, Settings
from daari.pricing import matching_model_key, resolve_price
import daari.pricing as pricing_mod


def _promo_entry(**extra: object) -> dict:
    body: dict = {
        "input_per_1m": 4.0,
        "output_per_1m": 20.0,
        "cached_input_per_1m": 0.40,
        "cache_write_30m_per_1m": 5.0,
        "cache_write_12h_per_1m": 10.0,
        "effective_to": "2026-11-21",
        "baseline": {
            "input_per_1m": 5.0,
            "output_per_1m": 30.0,
            "cached_input_per_1m": 0.50,
            "cache_write_30m_per_1m": 6.25,
            "cache_write_12h_per_1m": 12.50,
        },
    }
    body.update(extra)
    return body


def test_promo_rates_before_effective_to():
    pricing = PricingSettings(models={"promo-model": _promo_entry()})
    price = resolve_price(
        "promo-model",
        pricing,
        fallback_per_1k=0.002,
        now=date(2026, 11, 20),
    )
    assert price.input_per_1m == pytest.approx(4.0)
    assert price.output_per_1m == pytest.approx(20.0)
    assert price.cached_input_per_1m == pytest.approx(0.40)
    assert price.cache_write_30m_per_1m == pytest.approx(5.0)
    assert price.cache_write_12h_per_1m == pytest.approx(10.0)


def test_baseline_rates_on_and_after_effective_to():
    pricing = PricingSettings(models={"promo-model": _promo_entry()})
    for when in (date(2026, 11, 21), date(2026, 11, 25), datetime(2026, 11, 21, tzinfo=timezone.utc)):
        price = resolve_price(
            "promo-model",
            pricing,
            fallback_per_1k=0.002,
            now=when,
        )
        assert price.input_per_1m == pytest.approx(5.0), when
        assert price.output_per_1m == pytest.approx(30.0), when
        assert price.cached_input_per_1m == pytest.approx(0.50), when
        assert price.cache_write_30m_per_1m == pytest.approx(6.25), when
        assert price.cache_write_12h_per_1m == pytest.approx(12.50), when


def test_entry_without_effective_to_unchanged():
    pricing = PricingSettings(
        models={"plain": {"input_per_1m": 1.0, "output_per_1m": 2.0}}
    )
    price = resolve_price(
        "plain", pricing, fallback_per_1k=0.002, now=date(2099, 1, 1)
    )
    assert price.input_per_1m == pytest.approx(1.0)
    assert price.output_per_1m == pytest.approx(2.0)


def test_malformed_effective_to_keeps_top_level_and_warns(monkeypatch):
    events: list[tuple[str, dict]] = []
    pricing_mod._pricing_window_warnings.clear()

    def _capture(event: str, payload: dict) -> None:
        events.append((event, payload))

    monkeypatch.setattr("daari.gateway.request_log.log_gateway_event", _capture)
    pricing = PricingSettings(
        models={
            "bad-date": _promo_entry(effective_to="not-a-date"),
        }
    )
    price = resolve_price(
        "bad-date", pricing, fallback_per_1k=0.002, now=date(2026, 12, 1)
    )
    assert price.input_per_1m == pytest.approx(4.0)
    assert price.output_per_1m == pytest.approx(20.0)
    assert any(e == "pricing_effective_to_ignored" for e, _ in events)


def test_effective_to_without_baseline_keeps_top_level_and_warns(monkeypatch):
    events: list[tuple[str, dict]] = []
    pricing_mod._pricing_window_warnings.clear()

    def _capture(event: str, payload: dict) -> None:
        events.append((event, payload))

    monkeypatch.setattr("daari.gateway.request_log.log_gateway_event", _capture)
    entry = _promo_entry()
    del entry["baseline"]
    pricing = PricingSettings(models={"no-baseline": entry})
    price = resolve_price(
        "no-baseline", pricing, fallback_per_1k=0.002, now=date(2026, 12, 1)
    )
    assert price.input_per_1m == pytest.approx(4.0)
    assert price.output_per_1m == pytest.approx(20.0)
    assert any(e == "pricing_effective_to_ignored" for e, _ in events)


def test_malformed_warning_is_rate_limited(monkeypatch):
    events: list[str] = []
    pricing_mod._pricing_window_warnings.clear()

    def _capture(event: str, payload: dict) -> None:
        events.append(event)

    monkeypatch.setattr("daari.gateway.request_log.log_gateway_event", _capture)
    pricing = PricingSettings(
        models={"once": _promo_entry(effective_to="bogus")}
    )
    for _ in range(5):
        resolve_price("once", pricing, fallback_per_1k=0.002, now=date(2026, 12, 1))
    assert events.count("pricing_effective_to_ignored") == 1


def test_shipped_gpt56_promo_window_flips_at_boundary():
    settings = Settings()
    before = resolve_price(
        "gpt-5.6",
        settings.pricing,
        fallback_per_1k=0.002,
        now=date(2026, 11, 20),
    )
    after = resolve_price(
        "gpt-5.6-sol",
        settings.pricing,
        fallback_per_1k=0.002,
        now=date(2026, 11, 21),
    )
    assert before.input_per_1m == pytest.approx(4.0)
    assert before.output_per_1m == pytest.approx(20.0)
    assert before.cached_input_per_1m == pytest.approx(0.40)
    assert after.input_per_1m == pytest.approx(5.0)
    assert after.output_per_1m == pytest.approx(30.0)
    assert after.cached_input_per_1m == pytest.approx(0.50)
    assert after.cache_write_30m_per_1m == pytest.approx(6.25)
    assert after.cache_write_12h_per_1m == pytest.approx(12.50)


def test_longest_key_match_unchanged_across_window():
    settings = Settings()
    for when in (date(2026, 11, 20), date(2026, 11, 25)):
        assert matching_model_key("gpt-5.6-luna", settings.pricing.models) == "gpt-5.6-luna"
        luna = resolve_price(
            "gpt-5.6-luna", settings.pricing, fallback_per_1k=0.002, now=when
        )
        assert luna.input_per_1m == pytest.approx(0.20)
        sol = resolve_price(
            "gpt-5.6", settings.pricing, fallback_per_1k=0.002, now=when
        )
        assert sol.input_per_1m != pytest.approx(luna.input_per_1m)


def test_model_price_accepts_effective_to_and_baseline():
    price = ModelPrice(
        input_per_1m=4.0,
        output_per_1m=20.0,
        effective_to="2026-11-21T00:00:00Z",
        baseline=ModelPriceBaseline(
            input_per_1m=5.0,
            output_per_1m=30.0,
            cached_input_per_1m=0.50,
        ),
    )
    assert price.effective_to == "2026-11-21T00:00:00Z"
    assert price.baseline is not None
    assert price.baseline.input_per_1m == pytest.approx(5.0)
