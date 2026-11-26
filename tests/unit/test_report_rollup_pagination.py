"""Bounded + paginated report clients/users rollups (#1552)."""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

from daari.observability.postgres_usage import PostgresUsageLedger
from daari.observability.usage import (
    DEFAULT_ROLLUP_LIMIT,
    MAX_ROLLUP_LIMIT,
    UsageLedger,
    page_rollup,
)


def _seed_clients(ledger: UsageLedger, count: int) -> None:
    # client-000 gets the most requests so the requests-desc order is deterministic.
    for index in range(count):
        for _ in range(count - index):
            ledger.record(tier="L3", client_id=f"client-{index:03d}", prompt_chars=8)


def test_defaults_are_bounded():
    assert DEFAULT_ROLLUP_LIMIT == 100
    assert MAX_ROLLUP_LIMIT == 500


def test_page_rollup_truncates_and_reports_has_more():
    rows = [{"client_id": f"c{i}"} for i in range(7)]
    page, meta = page_rollup(rows, limit=3, offset=0)
    assert [r["client_id"] for r in page] == ["c0", "c1", "c2"]
    assert meta == {"total": 7, "limit": 3, "offset": 0, "has_more": True}

    page, meta = page_rollup(rows, limit=3, offset=6)
    assert [r["client_id"] for r in page] == ["c6"]
    assert meta == {"total": 7, "limit": 3, "offset": 6, "has_more": False}

    page, meta = page_rollup(rows, limit=3, offset=50)
    assert page == []
    assert meta["has_more"] is False


def test_page_rollup_clamps_limit_and_offset():
    rows = [{"client_id": f"c{i}"} for i in range(3)]
    _, meta = page_rollup(rows, limit=0, offset=-5)
    assert meta["limit"] == 1
    assert meta["offset"] == 0
    _, meta = page_rollup(rows, limit=MAX_ROLLUP_LIMIT * 10, offset=0)
    assert meta["limit"] == MAX_ROLLUP_LIMIT
    _, meta = page_rollup(rows, limit=None, offset=None)
    assert meta["limit"] == DEFAULT_ROLLUP_LIMIT
    assert meta["offset"] == 0


def test_by_client_default_limit_truncates(tmp_path: Path):
    ledger = UsageLedger(tmp_path / "usage.sqlite3")
    _seed_clients(ledger, DEFAULT_ROLLUP_LIMIT + 5)
    rows = ledger.by_client(days=1)
    assert len(rows) == DEFAULT_ROLLUP_LIMIT
    assert rows[0]["client_id"] == "client-000"


def test_by_client_offset_pages_in_order(tmp_path: Path):
    ledger = UsageLedger(tmp_path / "usage.sqlite3")
    _seed_clients(ledger, 7)
    first = ledger.by_client(days=1, limit=3, offset=0)
    second = ledger.by_client(days=1, limit=3, offset=3)
    third = ledger.by_client(days=1, limit=3, offset=6)
    assert [r["client_id"] for r in first] == ["client-000", "client-001", "client-002"]
    assert [r["client_id"] for r in second] == ["client-003", "client-004", "client-005"]
    assert [r["client_id"] for r in third] == ["client-006"]
    assert ledger.by_client(days=1, limit=3, offset=9) == []


def test_by_client_limit_none_returns_every_row(tmp_path: Path):
    ledger = UsageLedger(tmp_path / "usage.sqlite3")
    _seed_clients(ledger, DEFAULT_ROLLUP_LIMIT + 2)
    assert len(ledger.by_client(days=1, limit=None)) == DEFAULT_ROLLUP_LIMIT + 2


def test_by_client_limit_clamped(tmp_path: Path):
    ledger = UsageLedger(tmp_path / "usage.sqlite3")
    _seed_clients(ledger, 3)
    assert len(ledger.by_client(days=1, limit=MAX_ROLLUP_LIMIT * 4)) == 3
    assert len(ledger.by_client(days=1, limit=0)) == 1
    assert len(ledger.by_client(days=1, limit=2, offset=-1)) == 2


def test_by_user_limit_offset(tmp_path: Path):
    ledger = UsageLedger(tmp_path / "usage.sqlite3")
    for index in range(5):
        for _ in range(5 - index):
            ledger.record(tier="L3", client_id="key-a", user_id=f"user-{index}", prompt_chars=4)
    page = ledger.by_user(days=1, limit=2, offset=2)
    assert [r["user_id"] for r in page] == ["user-2", "user-3"]
    assert len(ledger.by_user(days=1)) == 5
    assert len(ledger.by_user(days=1, limit=None)) == 5


def test_by_user_default_limit_truncates(tmp_path: Path):
    ledger = UsageLedger(tmp_path / "usage.sqlite3")
    for index in range(DEFAULT_ROLLUP_LIMIT + 1):
        ledger.record(tier="L3", client_id="key-a", user_id=f"user-{index:03d}", prompt_chars=4)
    assert len(ledger.by_user(days=1)) == DEFAULT_ROLLUP_LIMIT
    assert len(ledger.by_user(days=1, limit=None)) == DEFAULT_ROLLUP_LIMIT + 1


class _FakeCursor:
    def __init__(self, rows: list[tuple[Any, ...]]) -> None:
        self._rows = rows
        self._last = ""

    def __enter__(self) -> _FakeCursor:
        return self

    def __exit__(self, *exc: Any) -> None:
        return None

    def execute(self, sql: str, params: Any = None) -> None:
        self._last = sql

    def fetchall(self) -> list[tuple[Any, ...]]:
        if "FROM client_usage" in self._last or "FROM user_usage" in self._last:
            return list(self._rows)
        return []


class _FakeConn:
    def __init__(self, rows: list[tuple[Any, ...]]) -> None:
        self._rows = rows

    def __enter__(self) -> _FakeConn:
        return self

    def __exit__(self, *exc: Any) -> None:
        return None

    def cursor(self) -> _FakeCursor:
        return _FakeCursor(self._rows)

    def commit(self) -> None:
        return None


def _pg_ledger(rows: list[tuple[Any, ...]]) -> PostgresUsageLedger:
    ledger = PostgresUsageLedger.__new__(PostgresUsageLedger)
    ledger.dsn = "postgresql://x/y"
    ledger.enabled = True
    ledger.unreachable = False
    ledger._lock = threading.Lock()
    ledger._connect = lambda: _FakeConn(rows)  # type: ignore[method-assign]
    return ledger


def test_postgres_by_client_pages():
    rows = [(f"client-{i:03d}", "L3", 10 - i, 0, 40, 40) for i in range(7)]
    ledger = _pg_ledger(rows)
    page = ledger.by_client(days=1, limit=3, offset=3)
    assert [r["client_id"] for r in page] == ["client-003", "client-004", "client-005"]
    assert ledger.by_client(days=1, limit=3, offset=9) == []
    assert len(ledger.by_client(days=1, limit=None)) == 7
    assert len(ledger.by_client(days=1)) == 7


def test_postgres_by_client_default_limit_truncates():
    rows = [(f"client-{i:03d}", "L3", 1000 - i, 0, 4, 4) for i in range(DEFAULT_ROLLUP_LIMIT + 3)]
    ledger = _pg_ledger(rows)
    assert len(ledger.by_client(days=1)) == DEFAULT_ROLLUP_LIMIT
    assert len(ledger.by_client(days=1, limit=MAX_ROLLUP_LIMIT)) == DEFAULT_ROLLUP_LIMIT + 3
    assert len(ledger.by_client(days=1, limit=None)) == DEFAULT_ROLLUP_LIMIT + 3


def test_postgres_by_user_pages():
    rows = [("key-a", f"user-{i}", "L3", 10 - i, 0, 4, 4) for i in range(5)]
    ledger = _pg_ledger(rows)
    page = ledger.by_user(days=1, limit=2, offset=1)
    assert [r["user_id"] for r in page] == ["user-1", "user-2"]
    assert len(ledger.by_user(days=1)) == 5
    assert ledger.by_user(days=1, limit=2, offset=5) == []
