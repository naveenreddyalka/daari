"""Cross-replica Postgres audit log (#483) — memory: fake, single hash chain."""

from __future__ import annotations

import uuid

from daari.config.settings import Settings
from daari.enterprise.audit import AuditLog
from daari.enterprise.postgres_audit import PostgresAuditLog, audit_log_from_settings


def _dsn() -> str:
    return f"memory:audit-{uuid.uuid4().hex}"


def test_two_writers_share_list_and_verify():
    dsn = _dsn()
    a = PostgresAuditLog(dsn)
    b = PostgresAuditLog(dsn)
    a.record(actor="ops", role="admin", action="keys.revoke", detail={"key_id": "k1"})
    b.record(actor="ops", role="admin", action="keys.create", detail={"key_id": "k2"})
    rows = a.list(limit=10)
    actions = {r["action"] for r in rows}
    assert actions == {"keys.revoke", "keys.create"}
    assert len(b.list(limit=10)) == 2
    result = b.verify()
    assert result.ok is True
    assert result.chained == 2
    assert result.legacy == 0


def test_audit_log_from_settings_selects_postgres():
    settings = Settings.model_validate(
        {
            "enterprise": {"audit_backend": "postgres"},
            "observability": {"postgres_url": _dsn()},
        }
    )
    log = audit_log_from_settings(settings)
    assert isinstance(log, PostgresAuditLog)


def test_audit_log_from_settings_defaults_sqlite(tmp_path):
    settings = Settings.model_validate(
        {"enterprise": {"audit_path": str(tmp_path / "audit.sqlite3")}}
    )
    log = audit_log_from_settings(settings)
    assert isinstance(log, AuditLog)


def test_postgres_audit_import_error_message():
    store = PostgresAuditLog("postgresql://x", enabled=False)
    store.enabled = True
    store._memory = False
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "psycopg" or name.startswith("psycopg."):
            raise ImportError("nope")
        return real_import(name, *args, **kwargs)

    builtins.__import__ = fake_import
    try:
        import pytest

        with pytest.raises(RuntimeError, match="psycopg"):
            store._connect()
    finally:
        builtins.__import__ = real_import
