"""Per-request spend rows and chargeback export (#709)."""

from __future__ import annotations

import json
import sqlite3

import pytest
from typer.testing import CliRunner

from daari.auth.virtual_keys import VirtualKey
from daari.cli.app import app as cli_app
from daari.config.settings import Settings
from daari.gateway.internal import RequestMeta
from daari.observability.spend import (
    PostgresSpendLedger,
    SpendContext,
    SpendLedger,
    bind_spend_context,
    install_spend_hook,
    spend_ledger_from_settings,
)
from daari.observability.usage import UsageLedger
from daari.server.auth import AuthClaims, apply_auth_claims_to_meta

OLD = "2026-01-01T00:00:00+00:00"
NEW = "2026-06-01T12:00:00+00:00"
SINCE = "2026-03-01T00:00:00+00:00"


def _row(ledger: SpendLedger, **overrides) -> None:
    payload = {
        "ts": NEW,
        "request_id": "req-new",
        "key_id": "key-a",
        "team_id": "team-1",
        "client_id": "client-a",
        "model": "llama3.2:3b",
        "tier": "L3",
        "input_tokens": 1000,
        "output_tokens": 200,
        "cached_tokens": 0,
        "cost_usd": 0.0,
        "cost_avoided_usd": 0.004,
        "cache_hit": False,
    }
    payload.update(overrides)
    ledger.record(**payload)


def test_disabled_ledger_writes_nothing(tmp_path):
    path = tmp_path / "spend.sqlite3"
    ledger = SpendLedger(path, enabled=False)
    _row(ledger)
    assert ledger.enabled is False
    assert not path.exists()
    assert list(ledger.iter_rows(since=SINCE)) == []


def test_usage_ledger_schema_unchanged_when_spend_off(tmp_path):
    usage_path = tmp_path / "ledger.sqlite3"
    spend_path = tmp_path / "spend.sqlite3"
    usage = UsageLedger(usage_path)
    usage.record(tier="L3", prompt_chars=40, completion_chars=8, client_id="c")
    assert not spend_path.exists()
    assert getattr(usage, "on_recorded", None) is None
    with sqlite3.connect(usage_path) as conn:
        names = {row[0] for row in conn.execute("SELECT name FROM sqlite_master")}
    assert "spend_requests" not in names


def test_export_filters_fixed_timestamps_key_and_team(tmp_path):
    ledger = SpendLedger(tmp_path / "spend.sqlite3", enabled=True)
    _row(ledger, ts=OLD, request_id="req-old", key_id="key-a", team_id="team-1")
    _row(ledger, ts=NEW, request_id="req-new", key_id="key-a", team_id="team-1", cache_hit=True)
    _row(
        ledger,
        ts=NEW,
        request_id="req-other",
        key_id="key-b",
        team_id="team-2",
        cost_avoided_usd=1.5,
    )

    rows = list(ledger.iter_rows(since=SINCE))
    assert [row["request_id"] for row in rows] == ["req-new", "req-other"]
    assert rows[0]["cache_hit"] is True
    assert rows[0]["input_tokens"] == 1000
    assert rows[0]["cost_avoided_usd"] == pytest.approx(0.004)

    only_key = list(ledger.iter_rows(since=SINCE, key_id="key-b"))
    assert [row["request_id"] for row in only_key] == ["req-other"]
    only_team = list(ledger.iter_rows(since=SINCE, team_id="team-1"))
    assert [row["request_id"] for row in only_team] == ["req-new"]


def test_prune_drops_rows_before_cutoff(tmp_path):
    ledger = SpendLedger(tmp_path / "spend.sqlite3", enabled=True)
    _row(ledger, ts=OLD, request_id="req-old")
    _row(ledger, ts=NEW, request_id="req-new")
    assert ledger.prune_before(SINCE, dry_run=True) == 1
    assert [row["request_id"] for row in ledger.iter_rows(since="2000-01-01T00:00:00+00:00")] == [
        "req-old",
        "req-new",
    ]
    assert ledger.prune_before(SINCE) == 1
    assert [row["request_id"] for row in ledger.iter_rows(since="2000-01-01T00:00:00+00:00")] == [
        "req-new"
    ]


def test_local_serve_records_avoided_not_spend(tmp_path):
    usage = UsageLedger(tmp_path / "ledger.sqlite3")
    spend = SpendLedger(tmp_path / "spend.sqlite3", enabled=True)
    install_spend_hook(usage, spend)
    settings = Settings()
    bind_spend_context(
        SpendContext(
            key_id="key-a",
            team_id="team-1",
            client_id="client-a",
            request_id="req-priced",
            requested_model="gpt-4o-mini",
            pricing=settings.pricing,
            fallback_per_1k=0.002,
        )
    )
    usage.record(
        tier="L3",
        model="llama3.2:3b",
        client_id="client-a",
        input_tokens=1_000_000,
        output_tokens=1_000_000,
        cached_tokens=0,
    )
    row = next(spend.iter_rows(since="2000-01-01T00:00:00+00:00"))
    assert row["request_id"] == "req-priced"
    assert row["key_id"] == "key-a"
    assert row["team_id"] == "team-1"
    assert row["model"] == "llama3.2:3b"
    assert row["cost_usd"] == pytest.approx(0.0)
    # gpt-4o-mini $0.15 / $0.60 per 1M.
    assert row["cost_avoided_usd"] == pytest.approx(0.75)


def test_frontier_row_keeps_cost_and_zero_avoided(tmp_path):
    spend = SpendLedger(tmp_path / "spend.sqlite3", enabled=True)
    settings = Settings()
    bind_spend_context(
        SpendContext(
            request_id="req-l6",
            requested_model="gpt-4o-mini",
            pricing=settings.pricing,
            fallback_per_1k=0.002,
        )
    )
    spend.record_from_usage(
        None,
        tier="L6",
        model="gpt-4o-mini",
        client_id="c",
        input_tokens=1_000_000,
        output_tokens=0,
        cached_tokens=0,
        cache_hit=False,
    )
    # record_from_usage reads the contextvar when ctx is None... wait, I pass None
    # and the method uses current context. Let me check implementation.
    row = next(spend.iter_rows(since="2000-01-01T00:00:00+00:00"))
    assert row["cost_usd"] == pytest.approx(0.15)
    assert row["cost_avoided_usd"] == pytest.approx(0.0)


def test_claims_copy_key_and_team_onto_request_meta():
    meta = RequestMeta()
    apply_auth_claims_to_meta(
        meta,
        AuthClaims(
            kind="virtual",
            key_id="key-a",
            client_id="client-a",
            virtual_key=VirtualKey(
                key_id="key-a",
                name="bot",
                prefix="dk",
                team_id="team-9",
            ),
        ),
    )
    assert meta.key_id == "key-a"
    assert meta.team_id == "team-9"
    explicit = RequestMeta(key_id="header-key")
    apply_auth_claims_to_meta(
        explicit,
        AuthClaims(
            kind="virtual",
            key_id="key-a",
            virtual_key=VirtualKey(key_id="key-a", name="bot", prefix="dk", team_id="team-9"),
        ),
    )
    assert explicit.key_id == "header-key"


def test_cli_export_csv_and_jsonl_use_fixed_since(tmp_path, monkeypatch):
    path = tmp_path / "spend.sqlite3"
    ledger = SpendLedger(path, enabled=True)
    _row(ledger, ts=OLD, request_id="req-old")
    _row(ledger, ts=NEW, request_id="req-new", key_id="key-a", team_id="team-1")
    settings = Settings.model_validate(
        {"usage": {"spend": {"enabled": True, "path": str(path)}}}
    )
    monkeypatch.setattr("daari.cli.app.get_settings", lambda: settings)
    runner = CliRunner()

    csv_result = runner.invoke(
        cli_app,
        ["spend", "export", "--since", SINCE, "--format", "csv", "--key", "key-a"],
    )
    assert csv_result.exit_code == 0, csv_result.output
    assert "req-old" not in csv_result.stdout
    assert "req-new" in csv_result.stdout
    assert csv_result.stdout.splitlines()[0].startswith("timestamp,")

    jsonl = runner.invoke(
        cli_app,
        ["spend", "export", "--since", SINCE, "--format", "jsonl", "--team", "team-1"],
    )
    assert jsonl.exit_code == 0, jsonl.output
    rows = [json.loads(line) for line in jsonl.stdout.splitlines() if line.strip()]
    assert len(rows) == 1
    assert rows[0]["request_id"] == "req-new"
    assert rows[0]["timestamp"] == NEW
    assert rows[0]["cache_hit"] is False


def test_cli_export_disabled_is_an_error(tmp_path, monkeypatch):
    settings = Settings.model_validate(
        {"usage": {"spend": {"enabled": False, "path": str(tmp_path / "spend.sqlite3")}}}
    )
    monkeypatch.setattr("daari.cli.app.get_settings", lambda: settings)
    result = CliRunner().invoke(
        cli_app,
        ["spend", "export", "--since", SINCE, "--format", "jsonl"],
    )
    assert result.exit_code != 0
    assert not (tmp_path / "spend.sqlite3").exists()


def test_postgres_backend_selected_when_configured():
    settings = Settings.model_validate(
        {
            "observability": {
                "backend": "postgres",
                "postgres_url": "postgresql://localhost/daari",
            },
            "usage": {"spend": {"enabled": True}},
        }
    )
    ledger = spend_ledger_from_settings(settings)
    assert isinstance(ledger, PostgresSpendLedger)


def test_sqlite_backend_when_spend_enabled(tmp_path):
    settings = Settings.model_validate(
        {
            "usage": {
                "path": str(tmp_path / "ledger.sqlite3"),
                "spend": {"enabled": True, "path": str(tmp_path / "spend.sqlite3")},
            }
        }
    )
    ledger = spend_ledger_from_settings(settings)
    assert isinstance(ledger, SpendLedger)
    assert ledger.enabled is True
