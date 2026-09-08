"""Audit log CLI: list + JSONL export (issue #345)."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from typer.testing import CliRunner

from daari.cli import app as cli_app
from daari.enterprise.audit import AuditLog, parse_since

NOW = datetime(2026, 9, 6, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def audit_path(tmp_path, monkeypatch) -> Path:
    path = tmp_path / "audit.sqlite3"
    monkeypatch.setattr(
        cli_app,
        "get_settings",
        lambda: type(
            "S",
            (),
            {"enterprise": type("E", (), {"audit_path": str(path)})()},
        )(),
    )
    return path


def _seed(path: Path) -> AuditLog:
    log = AuditLog(path)
    # Direct inserts so timestamps are deterministic.
    with log._connect() as conn:
        rows = [
            ("2026-09-01T10:00:00+00:00", "alice", "admin", "keys.create", {"name": "a"}),
            ("2026-09-05T10:00:00+00:00", "bob", "admin", "budget.alert", {"threshold": 0.8}),
            ("2026-09-06T11:00:00+00:00", "alice", "admin", "budget.alert_failed", {}),
            ("2026-09-06T11:30:00+00:00", "carol", "viewer", "auth.key_expired", {"key": "k"}),
        ]
        conn.executemany(
            "INSERT INTO audit (ts, actor, role, action, detail) VALUES (?, ?, ?, ?, ?)",
            [(ts, actor, role, action, json.dumps(detail)) for ts, actor, role, action, detail in rows],
        )
    return log


def test_parse_since_relative_and_iso():
    assert parse_since("7d", now=NOW) == (NOW - timedelta(days=7)).isoformat()
    assert parse_since("12h", now=NOW) == (NOW - timedelta(hours=12)).isoformat()
    assert parse_since("2026-09-01T00:00:00Z").startswith("2026-09-01T00:00:00")
    with pytest.raises(ValueError):
        parse_since("not-a-date")


def test_list_filters_actor_action_since(audit_path):
    _seed(audit_path)
    log = AuditLog(audit_path)
    by_actor = log.list(limit=50, actor="alice")
    assert [row["action"] for row in by_actor] == ["budget.alert_failed", "keys.create"]
    by_action = log.list(limit=50, action="budget.")
    assert {row["action"] for row in by_action} == {"budget.alert", "budget.alert_failed"}
    since = log.list(limit=50, since="2026-09-06T00:00:00+00:00")
    assert len(since) == 2
    assert since[0]["seq"] > since[1]["seq"]


def test_iter_rows_batches_and_jsonl_shape(audit_path):
    _seed(audit_path)
    log = AuditLog(audit_path)
    rows = list(log.iter_rows(batch_size=2))
    assert len(rows) == 4
    assert set(rows[0]) == {"seq", "ts", "actor", "role", "action", "detail"}
    assert rows[0]["seq"] == 4


def test_cli_list_json_and_export(audit_path, tmp_path):
    _seed(audit_path)
    runner = CliRunner()
    listed = runner.invoke(cli_app.app, ["audit", "list", "--json", "--action", "budget."])
    assert listed.exit_code == 0, listed.output
    payload = json.loads(listed.output)
    assert len(payload) == 2
    assert payload[0]["action"].startswith("budget.")

    out = tmp_path / "audit.jsonl"
    exported = runner.invoke(
        cli_app.app,
        ["audit", "export", "--format", "jsonl", "--out", str(out), "--since", "7d"],
    )
    assert exported.exit_code == 0, exported.output
    lines = out.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) >= 2
    first = json.loads(lines[0])
    assert set(first) == {"seq", "ts", "actor", "role", "action", "detail"}


def test_cli_disabled_or_empty(tmp_path, monkeypatch):
    missing = tmp_path / "missing" / "audit.sqlite3"
    monkeypatch.setattr(
        cli_app,
        "get_settings",
        lambda: type(
            "S",
            (),
            {"enterprise": type("E", (), {"audit_path": str(missing)})()},
        )(),
    )
    # Path parent is creatable — AuditLog enables. Empty list is fine.
    runner = CliRunner()
    result = runner.invoke(cli_app.app, ["audit", "list"])
    assert result.exit_code == 0
    assert "No audit rows" in result.output

    # Force disabled store.
    monkeypatch.setattr(
        cli_app,
        "_audit_log_from_settings",
        lambda: AuditLog(missing, enabled=False),
    )
    disabled = runner.invoke(cli_app.app, ["audit", "list"])
    assert disabled.exit_code == 1
    assert "disabled" in disabled.output.lower()
