"""Per-request user_id on spend rows and team-member chargeback rollup (#1132)."""

from __future__ import annotations

import json
import sqlite3

import pytest
from typer.testing import CliRunner

from daari.cli.app import app as cli_app
from daari.config.settings import Settings
from daari.gateway.internal import InternalRequest, Message, RequestMeta
from daari.observability.spend import (
    SpendContext,
    SpendLedger,
    bind_spend_context,
    export_dict,
    install_spend_hook,
)
from daari.observability.usage import UsageLedger
from daari.router.router import Router

SINCE = "2026-01-01T00:00:00+00:00"
TS = "2026-06-15T12:00:00+00:00"


def _frontier_row(ledger: SpendLedger, **overrides) -> None:
    payload = {
        "ts": TS,
        "request_id": "req-a",
        "key_id": "key-shared",
        "team_id": "team-x",
        "client_id": "client-a",
        "user_id": "alice",
        "model": "gpt-4o-mini",
        "tier": "L6",
        "input_tokens": 1_000_000,
        "output_tokens": 0,
        "cached_tokens": 0,
        "cost_usd": 0.15,
        "cost_avoided_usd": 0.0,
        "cache_hit": False,
    }
    payload.update(overrides)
    ledger.record(**payload)


def test_migrate_adds_nullable_user_id_column(tmp_path):
    path = tmp_path / "spend.sqlite3"
    with sqlite3.connect(path) as conn:
        conn.executescript(
            """
            CREATE TABLE spend_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT NOT NULL,
                request_id TEXT NOT NULL,
                key_id TEXT NOT NULL DEFAULT '',
                team_id TEXT NOT NULL DEFAULT '',
                client_id TEXT NOT NULL DEFAULT '',
                model TEXT NOT NULL DEFAULT '',
                tier TEXT NOT NULL DEFAULT '',
                input_tokens INTEGER NOT NULL DEFAULT 0,
                output_tokens INTEGER NOT NULL DEFAULT 0,
                cached_tokens INTEGER NOT NULL DEFAULT 0,
                cache_write_tokens INTEGER NOT NULL DEFAULT 0,
                cost_usd REAL NOT NULL DEFAULT 0,
                cost_avoided_usd REAL NOT NULL DEFAULT 0,
                cache_hit INTEGER NOT NULL DEFAULT 0
            );
            """
        )
    ledger = SpendLedger(path, enabled=True)
    assert ledger.enabled is True
    with sqlite3.connect(path) as conn:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(spend_requests)")}
    assert "user_id" in columns


def test_two_users_on_same_team_key_are_attributed_separately(tmp_path):
    ledger = SpendLedger(tmp_path / "spend.sqlite3", enabled=True)
    _frontier_row(
        ledger,
        request_id="req-alice",
        user_id="alice",
        cost_usd=0.10,
    )
    _frontier_row(
        ledger,
        request_id="req-bob",
        user_id="bob",
        cost_usd=0.05,
    )
    _frontier_row(
        ledger,
        request_id="req-other-team",
        team_id="team-y",
        user_id="carol",
        cost_usd=0.99,
    )

    team_rows = list(ledger.iter_rows(since=SINCE, team_id="team-x"))
    assert {row["user_id"] for row in team_rows} == {"alice", "bob"}
    assert sum(row["cost_usd"] for row in team_rows) == pytest.approx(0.15)

    alice = list(ledger.iter_rows(since=SINCE, team_id="team-x", user_id="alice"))
    assert [row["request_id"] for row in alice] == ["req-alice"]
    assert alice[0]["cost_usd"] == pytest.approx(0.10)

    rollup = ledger.by_user(since=SINCE, team_id="team-x")
    by_id = {entry["user_id"]: entry for entry in rollup}
    assert set(by_id) == {"alice", "bob"}
    assert by_id["alice"]["cost_usd"] == pytest.approx(0.10)
    assert by_id["bob"]["cost_usd"] == pytest.approx(0.05)
    assert by_id["alice"]["requests"] == 1
    assert sum(entry["cost_usd"] for entry in rollup) == pytest.approx(
        sum(row["cost_usd"] for row in team_rows)
    )


def test_record_from_usage_copies_user_id_from_spend_context(tmp_path):
    usage = UsageLedger(tmp_path / "ledger.sqlite3")
    spend = SpendLedger(tmp_path / "spend.sqlite3", enabled=True)
    install_spend_hook(usage, spend)
    settings = Settings()
    bind_spend_context(
        SpendContext(
            key_id="key-a",
            team_id="team-1",
            client_id="client-a",
            user_id="dana",
            request_id="req-user",
            requested_model="gpt-4o-mini",
            pricing=settings.pricing,
            fallback_per_1k=0.002,
        )
    )
    usage.record(
        tier="L6",
        model="gpt-4o-mini",
        client_id="client-a",
        user_id="dana",
        input_tokens=1_000_000,
        output_tokens=0,
    )
    row = next(spend.iter_rows(since=SINCE))
    assert row["user_id"] == "dana"
    assert row["team_id"] == "team-1"
    assert export_dict(row)["user_id"] == "dana"


def test_router_open_spend_context_includes_meta_user(tmp_path):
    spend = SpendLedger(tmp_path / "spend.sqlite3", enabled=True)
    router = Router.__new__(Router)
    router.spend_ledger = spend
    router.pricing = Settings().pricing
    router.frontier_price_per_1k_tokens = 0.002
    request = InternalRequest(
        model="gpt-4o-mini",
        messages=[Message(role="user", content="hi")],
        meta=RequestMeta(client_id="c", user="erin", key_id="k", team_id="t"),
    )
    router._open_spend_context(request, "req-erin")
    from daari.observability.spend import current_spend_context

    ctx = current_spend_context()
    assert ctx is not None
    assert ctx.user_id == "erin"
    assert ctx.team_id == "t"


def test_export_cli_includes_user_column_and_user_filter(tmp_path, monkeypatch):
    path = tmp_path / "spend.sqlite3"
    ledger = SpendLedger(path, enabled=True)
    _frontier_row(ledger, request_id="req-alice", user_id="alice", cost_usd=0.10)
    _frontier_row(ledger, request_id="req-bob", user_id="bob", cost_usd=0.05)
    settings = Settings.model_validate({"usage": {"spend": {"enabled": True, "path": str(path)}}})
    monkeypatch.setattr("daari.cli.app.get_settings", lambda: settings)
    runner = CliRunner()

    help_result = runner.invoke(
        cli_app,
        ["spend", "export", "--help"],
        env={"NO_COLOR": "1", "TERM": "dumb", "COLUMNS": "120"},
    )
    assert help_result.exit_code == 0
    help_text = help_result.stdout + help_result.stderr
    assert "--user" in help_text

    jsonl = runner.invoke(
        cli_app,
        [
            "spend",
            "export",
            "--since",
            SINCE,
            "--format",
            "jsonl",
            "--team",
            "team-x",
            "--user",
            "alice",
        ],
    )
    assert jsonl.exit_code == 0, jsonl.output
    rows = [json.loads(line) for line in jsonl.stdout.splitlines() if line.strip()]
    assert len(rows) == 1
    assert rows[0]["user_id"] == "alice"
    assert rows[0]["request_id"] == "req-alice"

    all_team = runner.invoke(
        cli_app,
        ["spend", "export", "--since", SINCE, "--format", "jsonl", "--team", "team-x"],
    )
    assert all_team.exit_code == 0, all_team.output
    team_rows = [json.loads(line) for line in all_team.stdout.splitlines() if line.strip()]
    assert {row["user_id"] for row in team_rows} == {"alice", "bob"}
    assert all("user_id" in row for row in team_rows)


def test_spend_report_by_user_for_team(tmp_path, monkeypatch):
    path = tmp_path / "spend.sqlite3"
    ledger = SpendLedger(path, enabled=True)
    _frontier_row(ledger, request_id="req-alice", user_id="alice", cost_usd=0.10)
    _frontier_row(ledger, request_id="req-bob", user_id="bob", cost_usd=0.05)
    _frontier_row(
        ledger,
        request_id="req-other",
        team_id="team-y",
        user_id="carol",
        cost_usd=0.99,
    )
    settings = Settings.model_validate({"usage": {"spend": {"enabled": True, "path": str(path)}}})
    monkeypatch.setattr("daari.cli.app.get_settings", lambda: settings)
    runner = CliRunner()

    result = runner.invoke(
        cli_app,
        ["spend", "report", "--since", SINCE, "--team", "team-x", "--by-user"],
    )
    assert result.exit_code == 0, result.output
    assert "alice" in result.stdout
    assert "bob" in result.stdout
    assert "carol" not in result.stdout
    assert "0.1000" in result.stdout or "0.10" in result.stdout
    assert "0.0500" in result.stdout or "0.05" in result.stdout


def test_export_without_user_flag_still_streams_all_rows(tmp_path, monkeypatch):
    """Additive: omit --user and every matching row still exports (with user_id)."""
    path = tmp_path / "spend.sqlite3"
    ledger = SpendLedger(path, enabled=True)
    _frontier_row(ledger, request_id="req-1", user_id="")
    _frontier_row(ledger, request_id="req-2", user_id="alice")
    settings = Settings.model_validate({"usage": {"spend": {"enabled": True, "path": str(path)}}})
    monkeypatch.setattr("daari.cli.app.get_settings", lambda: settings)
    result = CliRunner().invoke(
        cli_app,
        ["spend", "export", "--since", SINCE, "--format", "jsonl"],
    )
    assert result.exit_code == 0, result.output
    rows = [json.loads(line) for line in result.stdout.splitlines() if line.strip()]
    assert len(rows) == 2
    assert {row["request_id"] for row in rows} == {"req-1", "req-2"}
