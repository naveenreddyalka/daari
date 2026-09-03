"""Retention policy and prune (#332).

Stores grow forever unless an operator sets a retention window. 0 days means
keep forever so an upgrade never silently deletes data. A dry-run reports
what a real sweep would remove; the live sweep never fails a request.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone

import pytest
from typer.testing import CliRunner

from daari.cli.app import app as cli_app
from daari.config.settings import Settings
from daari.enterprise.audit import AuditLog
from daari.gateway.mcp_tasks import McpTaskStore
from daari.learning.feedback import FeedbackStore
from daari.observability.retention import (
    RETENTION_SWEEP_SECONDS,
    prune_all,
    run_sweep,
)
from daari.observability.trace import RequestTrace, TraceStore
from daari.observability.usage import UsageLedger

NOW = datetime(2026, 9, 3, 12, 0, tzinfo=timezone.utc)
OLD = (NOW - timedelta(days=40)).isoformat()
RECENT = (NOW - timedelta(days=2)).isoformat()


def _settings(tmp_path, **days: int) -> Settings:
    return Settings.model_validate(
        {
            "observability": {
                "retention": {
                    "traces_days": days.get("traces", 0),
                    "ledger_days": days.get("ledger", 0),
                    "audit_days": days.get("audit", 0),
                    "shadow_days": days.get("shadow", 0),
                    "tasks_days": days.get("tasks", 0),
                }
            },
            "trace": {"path": str(tmp_path / "traces.sqlite3")},
            "usage": {"path": str(tmp_path / "ledger.sqlite3")},
            "enterprise": {"audit_path": str(tmp_path / "audit.sqlite3")},
            "learning": {"path": str(tmp_path / "feedback.sqlite3")},
            "integrations": {"mcp_tasks": {"path": str(tmp_path / "tasks")}},
        }
    )


class TestSettings:
    def test_defaults_keep_forever(self):
        retention = Settings().observability.retention
        assert retention.traces_days == 0
        assert retention.ledger_days == 0
        assert retention.audit_days == 0
        assert retention.shadow_days == 0
        assert retention.tasks_days == 0
        assert retention.enabled is False
        assert RETENTION_SWEEP_SECONDS == 86400

    def test_negative_days_rejected(self):
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            Settings.model_validate({"observability": {"retention": {"traces_days": -1}}})


def _seed_trace(store: TraceStore, trace_id: str, ts: str) -> None:
    store.save(RequestTrace(trace_id), tier="L3", category="chat")
    with sqlite3.connect(store.path) as conn:
        conn.execute("UPDATE traces SET ts = ? WHERE trace_id = ?", (ts, trace_id))


class TestPrune:
    def test_zero_days_deletes_nothing(self, tmp_path):
        settings = _settings(tmp_path)
        traces = TraceStore(settings.trace.path)
        _seed_trace(traces, "old", OLD)
        results = prune_all(settings, now=NOW)
        by_store = {row.store: row for row in results}
        assert all(row.deleted == 0 and row.skipped for row in results)
        assert traces.get("old") is not None
        assert by_store["traces"].cutoff is None

    def test_traces_older_than_window_are_removed(self, tmp_path):
        settings = _settings(tmp_path, traces=30)
        traces = TraceStore(settings.trace.path)
        _seed_trace(traces, "old", OLD)
        _seed_trace(traces, "new", RECENT)
        results = prune_all(settings, now=NOW)
        row = next(r for r in results if r.store == "traces")
        assert row.deleted == 1 and not row.skipped
        assert traces.get("old") is None
        assert traces.get("new") is not None

    def test_ledger_prunes_by_day_on_both_tables(self, tmp_path):
        settings = _settings(tmp_path, ledger=7)
        ledger = UsageLedger(settings.usage.path)
        ledger.record(tier="L3", day="2026-07-01", client_id="c1", prompt_chars=40)
        ledger.record(tier="L3", day="2026-09-02", client_id="c1", prompt_chars=8)
        prune_all(settings, now=NOW)
        report = ledger.report(days=365)
        assert report["totals"]["requests"] == 1
        assert ledger.by_client(days=365)[0]["requests"] == 1

    def test_shadow_checks_are_pruned(self, tmp_path):
        settings = _settings(tmp_path, shadow=14)
        feedback = FeedbackStore(settings.learning.path)
        feedback.record_tier_shadow(
            category="chat", served_tier="L3", compare_tier="L5", similarity=0.9, agreed=True
        )
        with sqlite3.connect(feedback.path) as conn:
            conn.execute("UPDATE tier_shadow_checks SET ts = ?", (OLD,))
            conn.execute(
                "INSERT INTO shadow_checks (ts, category, similarity, agreed) VALUES (?,?,?,?)",
                (OLD, "chat", 0.5, 1),
            )
            conn.execute(
                "INSERT INTO shadow_checks (ts, category, similarity, agreed) VALUES (?,?,?,?)",
                (RECENT, "chat", 0.9, 1),
            )
        prune_all(settings, now=NOW)
        with sqlite3.connect(feedback.path) as conn:
            assert conn.execute("SELECT COUNT(*) FROM tier_shadow_checks").fetchone()[0] == 0
            assert conn.execute("SELECT COUNT(*) FROM shadow_checks").fetchone()[0] == 1

    def test_audit_prune_writes_summary_row(self, tmp_path):
        settings = _settings(tmp_path, audit=30)
        audit = AuditLog(settings.enterprise.audit_path)
        audit.record(actor="a", role="admin", action="old.event")
        with sqlite3.connect(audit.path) as conn:
            conn.execute("UPDATE audit SET ts = ?", (OLD,))
        prune_all(settings, now=NOW)
        rows = audit.list()
        assert any(row["action"] == "old.event" for row in rows) is False
        summary = [row for row in rows if row["action"] == "retention.prune"]
        assert len(summary) == 1
        detail = summary[0]["detail"]
        assert detail["audit"]["deleted"] == 1
        assert "cutoff" in detail["audit"]

    def test_tasks_older_than_window_are_removed(self, tmp_path):
        settings = _settings(tmp_path, tasks=1)
        store = McpTaskStore(settings.integrations.mcp_tasks.path)
        old = store.create(tool="slow")
        new = store.create(tool="fast")
        old.created_at = (NOW - timedelta(days=3)).timestamp()
        store._persist(old)
        prune_all(settings, now=NOW)
        reopened = McpTaskStore(settings.integrations.mcp_tasks.path)
        assert reopened.get(old.task_id) is None
        assert reopened.get(new.task_id) is not None

    def test_dry_run_counts_without_deleting(self, tmp_path):
        settings = _settings(tmp_path, traces=30, ledger=7)
        traces = TraceStore(settings.trace.path)
        _seed_trace(traces, "old", OLD)
        ledger = UsageLedger(settings.usage.path)
        ledger.record(tier="L3", day="2026-07-01", prompt_chars=4)
        results = prune_all(settings, now=NOW, dry_run=True)
        assert next(r for r in results if r.store == "traces").deleted == 1
        # usage + client_usage rows for the same request.
        assert next(r for r in results if r.store == "ledger").deleted == 2
        assert traces.get("old") is not None
        assert ledger.report(days=365)["totals"]["requests"] == 1


class TestSweepSafety:
    def test_sweep_failure_is_logged_not_raised(self, tmp_path, monkeypatch):
        from daari.observability import retention as mod

        events: list[tuple[str, dict]] = []
        monkeypatch.setattr(
            "daari.gateway.request_log.log_gateway_event",
            lambda name, detail=None: events.append((name, detail or {})),
        )

        def boom(*_a, **_k):
            raise RuntimeError("disk full")

        monkeypatch.setattr(mod, "prune_all", boom)
        assert run_sweep(_settings(tmp_path, traces=7), now=NOW) == []
        assert events[-1][0] == "retention.sweep_failed"
        assert "RuntimeError" in events[-1][1]["error"]

    def test_successful_sweep_is_logged(self, tmp_path, monkeypatch):
        events: list[tuple[str, dict]] = []
        monkeypatch.setattr(
            "daari.gateway.request_log.log_gateway_event",
            lambda name, detail=None: events.append((name, detail or {})),
        )
        run_sweep(_settings(tmp_path, traces=7), now=NOW)
        names = [name for name, _ in events]
        assert "retention.sweep" in names


class TestCLI:
    def test_prune_dry_run_prints_counts(self, tmp_path, monkeypatch):
        settings = _settings(tmp_path, traces=30)
        traces = TraceStore(settings.trace.path)
        _seed_trace(traces, "old", OLD)
        monkeypatch.setattr("daari.cli.app.get_settings", lambda: settings)
        result = CliRunner().invoke(cli_app, ["prune", "--dry-run"])
        assert result.exit_code == 0, result.output
        assert "traces" in result.output
        assert "1" in result.output
        assert traces.get("old") is not None

    def test_prune_applies(self, tmp_path, monkeypatch):
        settings = _settings(tmp_path, traces=30)
        traces = TraceStore(settings.trace.path)
        _seed_trace(traces, "old", OLD)
        monkeypatch.setattr("daari.cli.app.get_settings", lambda: settings)
        result = CliRunner().invoke(cli_app, ["prune"])
        assert result.exit_code == 0, result.output
        assert traces.get("old") is None


class TestPostgresHooks:
    def test_postgres_trace_store_exposes_prune(self):
        from daari.observability.postgres_trace import PostgresTraceStore

        store = PostgresTraceStore("postgresql://unused", enabled=False)
        assert store.prune_before(OLD, dry_run=True) == 0

    def test_postgres_ledger_exposes_prune(self):
        from daari.observability.postgres_usage import PostgresUsageLedger

        ledger = PostgresUsageLedger("postgresql://unused", enabled=False)
        assert ledger.prune_before_day("2026-01-01", dry_run=True) == 0
