"""Anthropic Usage/Cost Analytics spend reconcile (#2033)."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from daari.config.settings import Settings
from daari.enterprise.analytics_reconcile import (
    ANALYTICS_BETA,
    AnalyticsReconcileError,
    cents_to_usd,
    fetch_anthropic_cost_rows,
    format_reconcile_table,
    reconcile,
    resolve_anthropic_admin_key,
    validate_window,
)
from daari.observability.spend import SpendLedger


def test_cents_to_usd():
    assert cents_to_usd("41280.000000") == pytest.approx(412.80)
    assert cents_to_usd(None) == 0.0


def test_validate_window_rejects_over_31_days():
    with pytest.raises(AnalyticsReconcileError, match="31"):
        validate_window("2026-09-01T00:00:00Z", "2026-10-10T00:00:00Z")


def test_validate_window_ok_within_31_days():
    start, end = validate_window("2026-09-01T00:00:00Z", "2026-09-15T00:00:00Z")
    assert start.startswith("2026-09-01")
    assert end.startswith("2026-09-15")


def test_missing_admin_key_message():
    settings = Settings.model_validate({"frontier": {"enabled": False, "api_key": ""}})
    assert resolve_anthropic_admin_key(settings) == ""


def test_analytics_api_key_preferred(monkeypatch):
    settings = Settings.model_validate(
        {
            "frontier": {"enabled": True, "api_key": "sk-frontier"},
            "anthropic": {"analytics_api_key": "sk-admin"},
        }
    )
    assert resolve_anthropic_admin_key(settings) == "sk-admin"


def _transport(cost_amount: str = "100.000000", tokens: int = 50) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers.get("anthropic-beta") == ANALYTICS_BETA
        assert "x-api-key" in request.headers
        path = request.url.path
        if path.endswith("/analytics/cost"):
            return httpx.Response(
                200,
                json={
                    "data": [
                        {
                            "starting_at": "2026-09-03T00:00:00Z",
                            "ending_at": "2026-09-04T00:00:00Z",
                            "group": {"model": "claude-sonnet-4-5"},
                            "cost": {
                                "amount": cost_amount,
                                "list_amount": "120.000000",
                                "currency": "USD",
                            },
                        }
                    ],
                    "has_more": False,
                },
            )
        if path.endswith("/analytics/usage"):
            return httpx.Response(
                200,
                json={
                    "data": [
                        {
                            "starting_at": "2026-09-03T00:00:00Z",
                            "ending_at": "2026-09-04T00:00:00Z",
                            "group": {"model": "claude-sonnet-4-5"},
                            "usage": {"total_tokens": tokens},
                        }
                    ],
                    "has_more": False,
                },
            )
        return httpx.Response(404)

    return httpx.MockTransport(handler)


def test_fetch_cost_uses_beta_header():
    rows = fetch_anthropic_cost_rows(
        "sk-test",
        starting_at="2026-09-01T00:00:00Z",
        ending_at="2026-09-08T00:00:00Z",
        transport=_transport(),
    )
    assert len(rows) == 1
    assert rows[0]["group"]["model"] == "claude-sonnet-4-5"


def test_reconcile_table_and_threshold(tmp_path: Path):
    ledger = SpendLedger(tmp_path / "spend.sqlite3", enabled=True)
    ledger.record(
        ts="2026-09-03T12:00:00Z",
        request_id="r1",
        model="claude-sonnet-4-5",
        provider="anthropic",
        tier="L6",
        input_tokens=40,
        output_tokens=10,
        cost_usd=0.90,
    )
    # Provider amount 100 cents = $1.00; daari $0.90 → 10% drift
    result = reconcile(
        api_key="sk-test",
        ledger=ledger,
        since="2026-09-01T00:00:00Z",
        until="2026-09-08T00:00:00Z",
        threshold_pct=5.0,
        transport=_transport("100.000000", tokens=50),
    )
    assert len(result.rows) == 1
    row = result.rows[0]
    assert row.daari_cost_usd == pytest.approx(0.90)
    assert row.provider_amount_usd == pytest.approx(1.0)
    assert row.drift_pct == pytest.approx(10.0)
    assert result.exceeded
    table = format_reconcile_table(result.rows)
    assert "claude-sonnet-4-5" in table
    assert "0.9000" in table


def test_reconcile_quiet_within_threshold(tmp_path: Path):
    ledger = SpendLedger(tmp_path / "spend.sqlite3", enabled=True)
    ledger.record(
        ts="2026-09-03T12:00:00Z",
        request_id="r1",
        model="claude-sonnet-4-5",
        provider="anthropic",
        tier="L6",
        input_tokens=40,
        output_tokens=10,
        cost_usd=1.0,
    )
    result = reconcile(
        api_key="sk-test",
        ledger=ledger,
        since="2026-09-01T00:00:00Z",
        until="2026-09-08T00:00:00Z",
        threshold_pct=5.0,
        transport=_transport("100.000000"),
    )
    assert not result.exceeded


def test_fetch_without_key_raises():
    with pytest.raises(AnalyticsReconcileError, match="missing"):
        fetch_anthropic_cost_rows(
            "",
            starting_at="2026-09-01T00:00:00Z",
            ending_at="2026-09-08T00:00:00Z",
            transport=_transport(),
        )


def test_chargeback_docs_mention_reconcile():
    text = Path("docs/developer/guides/observability/chargeback.md").read_text(
        encoding="utf-8"
    )
    assert "spend reconcile" in text
    assert "analytics-usage-cost-2026-08-24" in text
