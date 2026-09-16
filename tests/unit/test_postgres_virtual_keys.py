"""Postgres virtual-key store for fleets (#544)."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from daari.auth.postgres_virtual_keys import (
    PostgresVirtualKeyStore,
    virtual_key_store_from_settings,
)
from daari.auth.virtual_keys import BudgetWindow, VirtualKeyStore
from daari.config.settings import Settings


def _dsn() -> str:
    return f"memory:vk-{uuid.uuid4().hex}"


def test_two_replicas_share_create_resolve_and_revoke():
    dsn = _dsn()
    a = PostgresVirtualKeyStore(dsn)
    b = PostgresVirtualKeyStore(dsn)
    created = a.create("bot", client_id="bot-a", team="eng")
    assert b.resolve(created.plaintext) is not None
    assert a.revoke(created.key.key_id) is True
    assert b.resolve(created.plaintext) is None


def test_rotate_grace_visible_on_second_replica():
    dsn = _dsn()
    a = PostgresVirtualKeyStore(dsn)
    b = PostgresVirtualKeyStore(dsn)
    created = a.create("bot", daily_budget_usd=1.0)
    old = created.plaintext
    rotated = a.rotate(created.key.key_id, grace="1h")
    assert b.resolve(rotated.plaintext) is not None
    assert b.resolve(old) is not None
    # After grace, old secret surfaces as expired (same #377 semantics).
    past = datetime.now(timezone.utc) + timedelta(hours=2)
    expired = b.resolve(old, now=past)
    assert expired is not None
    assert expired.is_expired(past)


def test_teams_and_report_by_team():
    dsn = _dsn()
    store = PostgresVirtualKeyStore(dsn)
    store.create_team("eng", budget_windows=[BudgetWindow("day", 5.0)])
    created = store.create("bot", team="eng", client_id="c1")
    assert store.get_team(name="eng") is not None
    assert created.key.team_name == "eng"
    assert "c1" in store.team_client_ids(created.key.team_id or "")
    report = store.report_by_team(
        [{"client_id": "c1", "requests": 3, "cache_hits": 1, "local_requests": 2,
          "frontier_requests": 1, "estimated_saved_usd": 0.5}]
    )
    assert report and report[0]["team"] == "eng"
    assert report[0]["requests"] == 3


def test_factory_selects_postgres_memory_and_sqlite(tmp_path, settings: Settings):
    settings.server.virtual_keys.path = str(tmp_path / "vk.sqlite3")
    settings.server.virtual_keys.backend = "sqlite"
    sqlite_store = virtual_key_store_from_settings(settings)
    assert isinstance(sqlite_store, VirtualKeyStore)

    settings.server.virtual_keys.backend = "postgres"
    settings.observability.postgres_url = _dsn()
    pg_store = virtual_key_store_from_settings(settings)
    assert isinstance(pg_store, PostgresVirtualKeyStore)
    created = pg_store.create("x")
    assert pg_store.resolve(created.plaintext) is not None


def test_postgres_import_error_message():
    store = PostgresVirtualKeyStore("postgresql://x", enabled=False)
    store.enabled = True
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "psycopg" or name.startswith("psycopg."):
            raise ImportError("nope")
        return real_import(name, *args, **kwargs)

    builtins.__import__ = fake_import
    try:
        with pytest.raises(RuntimeError, match="psycopg"):
            store._connect()
    finally:
        builtins.__import__ = real_import
