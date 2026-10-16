"""Ollama :cloud models are metered, not free local spend (#1707)."""

from __future__ import annotations

from pathlib import Path

import pytest

from daari.config.settings import PricingSettings, Settings
from daari.gateway.internal import DaariMeta
from daari.observability.spend import SpendContext, SpendLedger, bind_spend_context, install_spend_hook
from daari.observability.usage import UsageLedger
from daari.pricing import cost_usd, pricing_warnings


def test_priced_cloud_models_are_not_free_local_spend(tmp_path: Path):
    ledger = UsageLedger(tmp_path / "ledger.sqlite3")
    spend = SpendLedger(tmp_path / "spend.sqlite3", enabled=True)
    install_spend_hook(ledger, spend)
    pricing = PricingSettings(
        models={
            "clef:cloud": {"input_per_1m": 1.0, "output_per_1m": 2.0},
            "clef-flash:cloud": {"input_per_1m": 0.5, "output_per_1m": 1.0},
        }
    )
    bind_spend_context(
        SpendContext(
            request_id="req-clef",
            requested_model="clef:cloud",
            pricing=pricing,
            fallback_per_1k=0.002,
        )
    )
    ledger.record(
        tier="L5",
        model="clef:cloud",
        input_tokens=1_000_000,
        output_tokens=1_000_000,
    )
    bind_spend_context(
        SpendContext(
            request_id="req-flash",
            requested_model="clef-flash:cloud",
            pricing=pricing,
            fallback_per_1k=0.002,
        )
    )
    ledger.record(
        tier="L3",
        model="clef-flash:cloud",
        input_tokens=2_000_000,
        output_tokens=0,
    )
    ledger.record(
        tier="L4",
        model="llama3.1:8b",
        input_tokens=1_000_000,
        output_tokens=1_000_000,
    )
    expected_clef = cost_usd(
        "clef:cloud", 1_000_000, 1_000_000, pricing, fallback_per_1k=0.002
    )
    expected_flash = cost_usd(
        "clef-flash:cloud", 2_000_000, 0, pricing, fallback_per_1k=0.002
    )
    assert expected_clef == pytest.approx(3.0)
    assert expected_flash == pytest.approx(1.0)
    spend_total = ledger.frontier_spend_usd(pricing=pricing, fallback_per_1k=0.002)
    assert spend_total == pytest.approx(expected_clef + expected_flash)
    rows = {row["model"]: row for row in spend.iter_rows(since="2000-01-01T00:00:00+00:00")}
    assert rows["clef:cloud"]["cost_usd"] == pytest.approx(expected_clef)
    assert rows["clef:cloud"]["cost_avoided_usd"] == pytest.approx(0.0)
    assert rows["clef-flash:cloud"]["cost_usd"] == pytest.approx(expected_flash)
    assert rows["llama3.1:8b"]["cost_usd"] == pytest.approx(0.0)


def test_unpriced_cloud_model_uses_fallback_and_warns(tmp_path: Path):
    ledger = UsageLedger(tmp_path / "ledger.sqlite3")
    pricing = PricingSettings(models={})
    ledger.record(
        tier="L3",
        model="clef:cloud",
        input_tokens=1_000_000,
        output_tokens=500_000,
    )
    expected = cost_usd("clef:cloud", 1_000_000, 500_000, pricing, fallback_per_1k=0.002)
    assert expected > 0
    assert ledger.frontier_spend_usd(pricing=pricing, fallback_per_1k=0.002) == pytest.approx(
        expected
    )
    settings = Settings()
    settings.models.l3 = "clef:cloud"
    settings.models.l5 = "clef-flash:cloud"
    settings.pricing.models = {}
    warnings = pricing_warnings(settings)
    assert any("clef:cloud" in warning for warning in warnings)
    assert any("clef-flash:cloud" in warning for warning in warnings)

    from daari.pricing import apply_cloud_billing_warning

    meta = DaariMeta(tier="L3", model="clef:cloud", executor="ollama")
    apply_cloud_billing_warning(meta, pricing, fallback_per_1k=0.002)
    assert meta.warning
    assert "clef:cloud" in meta.warning
    assert "no price configured" in meta.warning

    priced = PricingSettings(
        models={"clef:cloud": {"input_per_1m": 1.0, "output_per_1m": 2.0}}
    )
    quiet = DaariMeta(tier="L3", model="clef:cloud", executor="ollama")
    apply_cloud_billing_warning(quiet, priced, fallback_per_1k=0.002)
    assert quiet.warning is None
