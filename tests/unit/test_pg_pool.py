"""Per-DSN Postgres connection pooling (#975)."""

from __future__ import annotations

from contextlib import contextmanager
from unittest.mock import MagicMock

import pytest

from daari.gateway import pg_pool


@pytest.fixture(autouse=True)
def _reset_pools():
    pg_pool.reset_postgres_pools_for_tests()
    yield
    pg_pool.reset_postgres_pools_for_tests()


def test_configure_postgres_pool_bounds():
    pg_pool.configure_postgres_pool(min_size=2, max_size=8)
    assert pg_pool._min_size == 2
    assert pg_pool._max_size == 8


def test_pooled_connection_reuses_pool_across_operations(monkeypatch):
    fake_conn = MagicMock(name="conn")
    calls: list[str] = []

    class FakePool:
        def __init__(self, *args, **kwargs):
            calls.append("create")
            self.kwargs = kwargs

        @contextmanager
        def connection(self):
            calls.append("checkout")
            yield fake_conn

        def close(self):
            calls.append("close")

    monkeypatch.setattr(pg_pool, "_require_psycopg", lambda: object())
    monkeypatch.setitem(
        __import__("sys").modules,
        "psycopg_pool",
        type("M", (), {"ConnectionPool": FakePool})(),
    )
    # Force import path used inside _get_pool.
    import types

    mod = types.ModuleType("psycopg_pool")
    mod.ConnectionPool = FakePool
    monkeypatch.setitem(__import__("sys").modules, "psycopg_pool", mod)

    dsn = "postgresql://example/db"
    with pg_pool.pooled_connection(dsn) as conn1:
        assert conn1 is fake_conn
    with pg_pool.pooled_connection(dsn) as conn2:
        assert conn2 is fake_conn

    assert calls.count("create") == 1, "same DSN must share one pool"
    assert calls.count("checkout") == 2
    pg_pool.close_postgres_pools()
    assert "close" in calls


def test_spend_store_uses_pooled_connection(monkeypatch):
    from daari.observability.spend import PostgresSpendLedger

    seen: list[str] = []

    @contextmanager
    def fake_pooled(dsn: str):
        seen.append(dsn)
        conn = MagicMock()
        yield conn

    monkeypatch.setattr("daari.gateway.pg_pool.pooled_connection", fake_pooled)
    store = PostgresSpendLedger.__new__(PostgresSpendLedger)
    store.dsn = "postgresql://x/y"
    with store._connect() as conn:
        assert conn is not None
    assert seen == ["postgresql://x/y"]
