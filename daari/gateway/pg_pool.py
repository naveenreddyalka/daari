"""Shared per-DSN psycopg connection pools for Postgres-backed stores (#975)."""

from __future__ import annotations

import threading
from contextlib import contextmanager
from typing import Any, Iterator

_lock = threading.Lock()
_pools: dict[str, Any] = {}
_min_size = 1
_max_size = 4


def configure_postgres_pool(*, min_size: int = 1, max_size: int = 4) -> None:
    """Set default pool bounds for pools created after this call."""
    global _min_size, _max_size
    _min_size = max(0, int(min_size))
    _max_size = max(_min_size or 1, int(max_size))


def _require_psycopg() -> Any:
    try:
        import psycopg
    except ImportError as exc:
        raise RuntimeError(
            "postgres backend requires psycopg — "
            "pip install 'psycopg[binary,pool]>=3' (or daari[postgres])"
        ) from exc
    return psycopg


def _get_pool(dsn: str) -> Any:
    with _lock:
        pool = _pools.get(dsn)
        if pool is not None:
            return pool
        _require_psycopg()
        try:
            from psycopg_pool import ConnectionPool
        except ImportError as exc:
            raise RuntimeError(
                "postgres pooling requires psycopg_pool — "
                "pip install 'psycopg[binary,pool]>=3' (or daari[postgres])"
            ) from exc
        pool = ConnectionPool(
            conninfo=dsn,
            min_size=_min_size,
            max_size=_max_size,
            open=True,
        )
        _pools[dsn] = pool
        return pool


@contextmanager
def pooled_connection(dsn: str) -> Iterator[Any]:
    """Yield a connection from the per-DSN pool (reconnects after Postgres restarts)."""
    pool = _get_pool(dsn)
    with pool.connection() as conn:
        yield conn


def close_postgres_pools() -> None:
    """Close every pooled connection; safe to call from app shutdown."""
    with _lock:
        pools = list(_pools.values())
        _pools.clear()
    for pool in pools:
        try:
            pool.close()
        except Exception:
            pass


def reset_postgres_pools_for_tests() -> None:
    """Drop pool registry between tests (does not require psycopg_pool)."""
    close_postgres_pools()
    configure_postgres_pool(min_size=1, max_size=4)
