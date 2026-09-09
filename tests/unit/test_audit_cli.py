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
    assert {"seq", "ts", "actor", "role", "action", "detail"} <= set(rows[0])
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
    assert {"seq", "ts", "actor", "role", "action", "detail"} <= set(first)


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


# --- hash chain (#378) ------------------------------------------------------


def test_chain_verifies_clean(tmp_path):
    log = AuditLog(tmp_path / "audit.sqlite3")
    for index in range(3):
        log.record(actor="alice", role="admin", action="keys.create", detail={"n": index})
    result = log.verify()
    assert result.ok
    assert result.total == 3
    assert result.chained == 3
    assert result.legacy == 0


def test_edit_detail_breaks_at_seq(tmp_path):
    log = AuditLog(tmp_path / "audit.sqlite3")
    log.record(actor="alice", role="admin", action="keys.create", detail={"n": 1})
    log.record(actor="alice", role="admin", action="keys.create", detail={"n": 2})
    with log._connect() as conn:
        conn.execute("UPDATE audit SET detail = ? WHERE seq = 2", (json.dumps({"n": 99}),))
    result = log.verify()
    assert not result.ok
    assert result.broken_seq == 2
    assert result.reason == "hash_mismatch"


def test_mid_chain_delete_detected(tmp_path):
    log = AuditLog(tmp_path / "audit.sqlite3")
    for index in range(3):
        log.record(actor="alice", role="admin", action="keys.create", detail={"n": index})
    with log._connect() as conn:
        conn.execute("DELETE FROM audit WHERE seq = 2")
    result = log.verify()
    assert not result.ok
    assert result.reason == "seq_gap"
    assert result.broken_seq == 3


def test_legacy_plus_chained_verifies(tmp_path):
    path = tmp_path / "audit.sqlite3"
    _seed(path)  # legacy inserts without hashes
    log = AuditLog(path)
    log.record(actor="dave", role="admin", action="keys.rotate", detail={"key_id": "abc"})
    result = log.verify()
    assert result.ok
    assert result.legacy == 4
    assert result.chained == 1


def test_prune_then_verify(tmp_path):
    log = AuditLog(tmp_path / "audit.sqlite3")
    with log._connect() as conn:
        conn.execute(
            "INSERT INTO audit (ts, actor, role, action, detail) VALUES (?, ?, ?, ?, ?)",
            ("2020-01-01T00:00:00+00:00", "old", "admin", "keys.create", "{}"),
        )
    log.record(actor="alice", role="admin", action="keys.create", detail={"n": 1})
    log.record(actor="alice", role="admin", action="keys.create", detail={"n": 2})
    assert log.verify().ok
    pruned = log.prune_before("2025-01-01T00:00:00+00:00")
    assert pruned >= 1
    result = log.verify()
    assert result.ok
    assert result.chained >= 1


def test_cli_verify_json(audit_path):
    log = AuditLog(audit_path)
    log.record(actor="alice", role="admin", action="keys.create", detail={})
    runner = CliRunner()
    ok = runner.invoke(cli_app.app, ["audit", "verify", "--json"])
    assert ok.exit_code == 0, ok.output
    payload = json.loads(ok.output)
    assert payload["ok"] is True
    assert payload["chained"] >= 1

    with log._connect() as conn:
        conn.execute("UPDATE audit SET detail = ? WHERE row_hash IS NOT NULL", ('{"x":1}',))
    bad = runner.invoke(cli_app.app, ["audit", "verify", "--json"])
    assert bad.exit_code == 1
    assert json.loads(bad.output)["ok"] is False


def test_export_includes_hash_fields(audit_path, tmp_path):
    log = AuditLog(audit_path)
    log.record(actor="alice", role="admin", action="keys.create", detail={"n": 1})
    runner = CliRunner()
    out = tmp_path / "out.jsonl"
    exported = runner.invoke(
        cli_app.app, ["audit", "export", "--format", "jsonl", "--out", str(out)]
    )
    assert exported.exit_code == 0
    chained = [json.loads(line) for line in out.read_text().splitlines() if line]
    hashed = [row for row in chained if row.get("row_hash")]
    assert hashed
    assert hashed[0]["prev_hash"]
    assert hashed[0]["row_hash"]
