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
    assert "--credential" in text
    assert "credential_source" in text


def _record_anthropic(ledger: SpendLedger, request_id: str, cost: float, **kwargs) -> None:
    ledger.record(
        ts="2026-09-03T12:00:00Z",
        request_id=request_id,
        model="claude-sonnet-4-5",
        provider="anthropic",
        tier="L6",
        input_tokens=40,
        output_tokens=10,
        cost_usd=cost,
        **kwargs,
    )


def test_reconcile_excludes_tenant_credential_rows_by_default(tmp_path: Path):
    """Team/key BYOK rows bill another org: never compare them to the operator invoice (#2315)."""
    ledger = SpendLedger(tmp_path / "spend.sqlite3", enabled=True)
    _record_anthropic(ledger, "g1", 1.0, credential_source="global")
    _record_anthropic(ledger, "t1", 0.50, credential_source="team")
    _record_anthropic(ledger, "k1", 0.25, credential_source="key")
    result = reconcile(
        api_key="sk-test",
        ledger=ledger,
        since="2026-09-01T00:00:00Z",
        until="2026-09-08T00:00:00Z",
        threshold_pct=5.0,
        transport=_transport("100.000000", tokens=50),
    )
    assert result.credential == "global"
    assert len(result.rows) == 1
    row = result.rows[0]
    assert row.daari_cost_usd == pytest.approx(1.0)
    assert row.daari_tokens == 50
    assert row.drift_pct == pytest.approx(0.0)
    assert not result.exceeded
    assert result.excluded.rows == 2
    assert result.excluded.cost_usd == pytest.approx(0.75)
    assert result.excluded.tokens == 100
    assert result.excluded.by_source == {
        "key": pytest.approx(0.25),
        "team": pytest.approx(0.50),
    }


def test_reconcile_legacy_rows_without_credential_source_count_as_global(tmp_path: Path):
    """Regression pin: pre-column rows ('' source) keep the old drift math."""
    ledger = SpendLedger(tmp_path / "spend.sqlite3", enabled=True)
    _record_anthropic(ledger, "legacy", 0.90)
    result = reconcile(
        api_key="sk-test",
        ledger=ledger,
        since="2026-09-01T00:00:00Z",
        until="2026-09-08T00:00:00Z",
        threshold_pct=5.0,
        transport=_transport("100.000000", tokens=50),
    )
    assert len(result.rows) == 1
    assert result.rows[0].daari_cost_usd == pytest.approx(0.90)
    assert result.rows[0].drift_pct == pytest.approx(10.0)
    assert result.exceeded
    assert result.excluded.rows == 0
    assert result.excluded.cost_usd == 0.0
    assert result.excluded.by_source == {}


@pytest.mark.parametrize(
    ("scope", "expected_cost", "expected_excluded"),
    [("team", 0.50, 1.25), ("key", 0.25, 1.50), ("all", 1.75, 0.0)],
)
def test_reconcile_credential_scope_selects_rows(
    tmp_path: Path, scope: str, expected_cost: float, expected_excluded: float
):
    ledger = SpendLedger(tmp_path / "spend.sqlite3", enabled=True)
    _record_anthropic(ledger, "g1", 1.0, credential_source="global")
    _record_anthropic(ledger, "t1", 0.50, credential_source="team")
    _record_anthropic(ledger, "k1", 0.25, credential_source="key")
    result = reconcile(
        api_key="sk-test",
        ledger=ledger,
        since="2026-09-01T00:00:00Z",
        until="2026-09-08T00:00:00Z",
        threshold_pct=5.0,
        transport=_transport("100.000000", tokens=50),
        credential=scope,
    )
    assert result.credential == scope
    assert result.rows[0].daari_cost_usd == pytest.approx(expected_cost)
    assert result.excluded.cost_usd == pytest.approx(expected_excluded)


def test_reconcile_rejects_unknown_credential_scope(tmp_path: Path):
    ledger = SpendLedger(tmp_path / "spend.sqlite3", enabled=True)
    with pytest.raises(AnalyticsReconcileError, match="credential"):
        reconcile(
            api_key="sk-test",
            ledger=ledger,
            since="2026-09-01T00:00:00Z",
            until="2026-09-08T00:00:00Z",
            transport=_transport(),
            credential="vendor",
        )


def test_format_excluded_summary_lists_sources():
    from daari.enterprise.analytics_reconcile import ExcludedSpend, format_excluded_summary

    none = ExcludedSpend(rows=0, cost_usd=0.0, tokens=0, by_source={})
    assert format_excluded_summary(none, credential="global") == ""
    some = ExcludedSpend(
        rows=3, cost_usd=0.75, tokens=150, by_source={"key": 0.25, "team": 0.5}
    )
    text = format_excluded_summary(some, credential="global")
    assert "3" in text
    assert "0.7500" in text
    assert "team" in text and "key" in text
    assert "global" in text


def test_spend_reconcile_cli_credential_flag_and_excluded_line(monkeypatch, tmp_path: Path):
    from typer.testing import CliRunner

    from daari.cli.app import app
    from daari.config import settings as settings_mod

    ledger = SpendLedger(tmp_path / "spend.sqlite3", enabled=True)
    _record_anthropic(ledger, "g1", 1.0, credential_source="global")
    _record_anthropic(ledger, "t1", 0.50, credential_source="team")
    monkeypatch.setattr(
        "daari.observability.spend.spend_ledger_from_settings", lambda _s: ledger
    )
    monkeypatch.setattr(
        "daari.enterprise.analytics_reconcile.resolve_anthropic_admin_key",
        lambda _s: "sk-admin",
    )
    import daari.enterprise.analytics_reconcile as mod

    real_fetch_cost = mod.fetch_anthropic_cost_rows
    real_fetch_usage = mod.fetch_anthropic_usage_rows
    monkeypatch.setattr(
        mod,
        "fetch_anthropic_cost_rows",
        lambda key, **kw: real_fetch_cost(key, **{**kw, "transport": _transport()}),
    )
    monkeypatch.setattr(
        mod,
        "fetch_anthropic_usage_rows",
        lambda key, **kw: real_fetch_usage(key, **{**kw, "transport": _transport()}),
    )
    settings = Settings.model_validate(
        {"usage": {"spend": {"enabled": True, "path": str(tmp_path / "spend.sqlite3")}}}
    )
    monkeypatch.setattr(settings_mod, "get_settings", lambda: settings)
    monkeypatch.setattr("daari.cli.app.get_settings", lambda: settings)
    runner = CliRunner()
    window = [
        "--since",
        "2026-09-01T00:00:00Z",
        "--until",
        "2026-09-08T00:00:00Z",
    ]
    default = runner.invoke(app, ["spend", "reconcile", "--provider", "anthropic", *window])
    assert default.exit_code == 0, default.output
    assert "1.0000" in default.output
    assert "excluded" in default.output.lower()
    assert "0.5000" in default.output
    team = runner.invoke(
        app,
        ["spend", "reconcile", "--provider", "anthropic", *window, "--credential", "team"],
    )
    # Team rows ($0.50) against the operator invoice ($1.00) drift 50%.
    assert team.exit_code == 1, team.output
    assert "0.5000" in team.output
    bad = runner.invoke(
        app,
        ["spend", "reconcile", "--provider", "anthropic", *window, "--credential", "vendor"],
    )
    assert bad.exit_code != 0
    assert "credential" in (bad.output + str(bad.exception or "")).lower()
