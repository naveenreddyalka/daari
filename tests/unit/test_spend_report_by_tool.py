"""Spend report --by-tool rollup for MCP / provider chargeback (#1217)."""

from __future__ import annotations

from typer.testing import CliRunner

from daari.cli.app import app as cli_app
from daari.observability.spend import SpendLedger

SINCE = "2026-01-01T00:00:00+00:00"
TS = "2026-06-15T12:00:00+00:00"


def _row(ledger: SpendLedger, **overrides) -> None:
    payload = {
        "ts": TS,
        "request_id": "req-a",
        "key_id": "key-1",
        "team_id": "team-x",
        "client_id": "client-a",
        "user_id": "alice",
        "model": "gpt-4o-mini",
        "provider": "",
        "tier": "L6",
        "input_tokens": 1000,
        "output_tokens": 0,
        "cost_usd": 0.10,
        "cost_avoided_usd": 0.0,
        "cache_hit": False,
    }
    payload.update(overrides)
    ledger.record(**payload)


def test_by_tool_aggregates_mixed_chat_and_mcp(tmp_path):
    ledger = SpendLedger(tmp_path / "spend.sqlite3", enabled=True)
    _row(ledger, request_id="c1", model="gpt-4o-mini", provider="", cost_usd=0.10)
    _row(ledger, request_id="c2", model="gpt-4o-mini", provider="", cost_usd=0.05)
    _row(
        ledger,
        request_id="m1",
        model="daari",
        provider="mcp:weather",
        tier="mcp",
        cost_usd=0.02,
    )
    _row(
        ledger,
        request_id="m2",
        model="daari",
        provider="mcp:weather",
        tier="mcp",
        cost_usd=0.03,
    )
    _row(
        ledger,
        request_id="m3",
        model="daari",
        provider="mcp:stats",
        tier="mcp",
        cost_usd=0.01,
    )
    rollup = {row["tool"]: row for row in ledger.by_tool(since=SINCE)}
    assert rollup["gpt-4o-mini"]["requests"] == 2
    assert abs(rollup["gpt-4o-mini"]["cost_usd"] - 0.15) < 1e-9
    assert rollup["mcp:weather"]["requests"] == 2
    assert abs(rollup["mcp:weather"]["cost_usd"] - 0.05) < 1e-9
    assert rollup["mcp:stats"]["requests"] == 1
    assert abs(rollup["mcp:stats"]["cost_usd"] - 0.01) < 1e-9


def test_spend_report_by_tool_cli(tmp_path, monkeypatch):
    spend_path = tmp_path / "spend.sqlite3"
    ledger = SpendLedger(spend_path, enabled=True)
    _row(ledger, provider="mcp:weather", model="daari", tier="mcp", cost_usd=0.07)
    _row(ledger, provider="", model="gpt-4o-mini", cost_usd=0.20)

    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("DAARI_USAGE__SPEND__ENABLED", "true")
    monkeypatch.setenv("DAARI_USAGE__SPEND__PATH", str(spend_path))
    from daari.config.settings import get_settings

    get_settings.cache_clear()
    result = CliRunner().invoke(
        cli_app,
        ["spend", "report", "--since", SINCE, "--by-tool"],
    )
    assert result.exit_code == 0, result.output
    assert "mcp:weather" in result.output
    assert "gpt-4o-mini" in result.output
    assert "0.0700" in result.output or "0.07" in result.output
