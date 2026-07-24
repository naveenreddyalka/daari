"""F4 postgres backend selection (issue #116) — no live Postgres required."""

from __future__ import annotations

import pytest

from daari.observability.postgres_trace import PostgresTraceStore
from daari.observability.postgres_usage import PostgresUsageLedger
from daari.observability.trace import TraceStore
from daari.observability.usage import UsageLedger
from daari.router.router import AppContext


def test_default_sqlite_backends(settings, tmp_path):
    settings.usage.path = str(tmp_path / "ledger.sqlite3")
    settings.trace.path = str(tmp_path / "traces.sqlite3")
    settings.observability.backend = "sqlite"
    ctx = AppContext.from_settings(settings)
    assert isinstance(ctx.router.usage_ledger, UsageLedger)
    assert isinstance(ctx.router.trace_store, TraceStore)


def test_postgres_backend_selected_without_psycopg(settings, monkeypatch):
    settings.observability.backend = "postgres"
    settings.observability.postgres_url = "postgresql://localhost/daari"
    # Construction disables itself when connect fails — still returns postgres types.
    ctx = AppContext.from_settings(settings)
    assert isinstance(ctx.router.usage_ledger, PostgresUsageLedger)
    assert isinstance(ctx.router.trace_store, PostgresTraceStore)


def test_postgres_import_error_message():
    ledger = PostgresUsageLedger("postgresql://x", enabled=False)
    ledger.enabled = True
    with pytest.raises(RuntimeError, match="psycopg"):
        # Force connect path without the package by stubbing import.
        import builtins

        real_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == "psycopg" or name.startswith("psycopg."):
                raise ImportError("nope")
            return real_import(name, *args, **kwargs)

        builtins.__import__ = fake_import
        try:
            ledger._connect()
        finally:
            builtins.__import__ = real_import
