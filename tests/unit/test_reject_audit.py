"""Audit rows for budget 402 / rate-limit 429 / concurrency 503 (#1616)."""

from __future__ import annotations

import uuid
from pathlib import Path

from daari.config.settings import Settings
from daari.enterprise.audit import (
    AuditLog,
    record_budget_exceeded,
    record_concurrency_exceeded,
    record_rate_limit_exceeded,
)
from daari.enterprise.postgres_audit import PostgresAuditLog, audit_log_from_settings


def test_reject_helpers_write_stable_actions_sqlite(tmp_path: Path):
    audit = AuditLog(tmp_path / "audit.db")
    record_budget_exceeded(
        audit,
        key_id="k1",
        team_id="t1",
        scope="key",
        window="day",
        remaining=0,
        limit=10,
        quota="usd",
    )
    record_rate_limit_exceeded(
        audit,
        key_id="k1",
        team_id="t1",
        model="llama3.2:3b",
        scope="rpm",
        bucket="key",
        remaining=0,
        limit=60,
    )
    record_concurrency_exceeded(
        audit,
        key_id="k1",
        scope="key_concurrency",
        remaining=0,
        limit=1,
    )
    actions = {row["action"] for row in audit.list(limit=20)}
    assert actions == {
        "budget.exceeded",
        "rate_limit.exceeded",
        "concurrency.exceeded",
    }
    budget = next(r for r in audit.list(limit=20) if r["action"] == "budget.exceeded")
    assert budget["detail"]["key_id"] == "k1"
    assert budget["detail"]["team_id"] == "t1"
    assert "Authorization" not in str(budget)
    assert "sk-" not in str(budget)
    assert "prompt" not in str(budget).lower()


def test_reject_helpers_write_postgres_memory():
    dsn = f"memory:reject-audit-{uuid.uuid4().hex}"
    audit = PostgresAuditLog(dsn)
    record_budget_exceeded(audit, key_id="k2", scope="team", window="month", remaining=0)
    record_rate_limit_exceeded(audit, key_id="k2", scope="tpm", remaining=0, limit=1000)
    record_concurrency_exceeded(audit, key_id="k2", scope="concurrency", remaining=0, limit=2)
    rows = audit.list(limit=20)
    actions = {r["action"] for r in rows}
    assert "budget.exceeded" in actions
    assert "rate_limit.exceeded" in actions
    assert "concurrency.exceeded" in actions
    settings = Settings.model_validate(
        {
            "enterprise": {"audit_backend": "postgres"},
            "observability": {"postgres_url": dsn},
        }
    )
    assert isinstance(audit_log_from_settings(settings), PostgresAuditLog)


def test_auth_guide_lists_reject_audit_actions():
    text = (
        Path(__file__).resolve().parents[2]
        / "docs/developer/guides/configuration/auth-and-keys.md"
    ).read_text(encoding="utf-8")
    assert "budget.exceeded" in text
    assert "rate_limit.exceeded" in text
    assert "concurrency.exceeded" in text
