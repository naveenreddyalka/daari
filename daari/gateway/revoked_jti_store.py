"""Durable MCP OAuth revoked-jti denylist for multi-replica fleets (#1498).

Backends:
- in-process dict (default single-pod)
- Postgres via ``observability.postgres_url`` (``memory:<name>`` for tests)
- Redis when ``cache.backend=redis``

Entries TTL at token ``exp``; expired jtis are pruned on access. Revoke state
is not backup-critical (bounded by access-token lifetime).
"""

from __future__ import annotations

import threading
import time
from typing import Any, Protocol

_SCHEMA = """
CREATE TABLE IF NOT EXISTS daari_mcp_revoked_jti (
    jti TEXT PRIMARY KEY,
    exp BIGINT NOT NULL
)
"""

_MEMORY: dict[str, dict[str, int]] = {}
_MEMORY_LOCKS: dict[str, threading.Lock] = {}
_MEMORY_META_LOCK = threading.Lock()


def _memory_bucket(dsn: str) -> tuple[dict[str, int], threading.Lock]:
    with _MEMORY_META_LOCK:
        if dsn not in _MEMORY:
            _MEMORY[dsn] = {}
            _MEMORY_LOCKS[dsn] = threading.Lock()
        return _MEMORY[dsn], _MEMORY_LOCKS[dsn]


class RevokedJtiStore(Protocol):
    def is_revoked(self, jti: str, *, now: int | None = None) -> bool: ...

    def revoke(self, jti: str, exp: int, *, now: int | None = None) -> None: ...

    def clear(self) -> None: ...

    def prune(self, *, now: int | None = None) -> None: ...


class InProcessRevokedJtiStore:
    """Process-local denylist (default when no shared Redis/Postgres)."""

    def __init__(self) -> None:
        self._items: dict[str, int] = {}
        self._lock = threading.Lock()

    def prune(self, *, now: int | None = None) -> None:
        ts = int(time.time()) if now is None else int(now)
        with self._lock:
            stale = [jti for jti, exp in self._items.items() if exp < ts]
            for jti in stale:
                self._items.pop(jti, None)

    def is_revoked(self, jti: str, *, now: int | None = None) -> bool:
        if not jti:
            return False
        self.prune(now=now)
        with self._lock:
            return jti in self._items

    def revoke(self, jti: str, exp: int, *, now: int | None = None) -> None:
        ts = int(time.time()) if now is None else int(now)
        if not jti or int(exp) < ts:
            return
        with self._lock:
            self._items[jti] = int(exp)
        self.prune(now=ts)

    def clear(self) -> None:
        with self._lock:
            self._items.clear()


class PostgresRevokedJtiStore:
    """Shared denylist via Postgres (or ``memory:<name>`` for unit tests)."""

    def __init__(self, dsn: str) -> None:
        self.dsn = dsn
        self._lock = threading.Lock()
        self._memory = dsn.startswith("memory:")
        self.enabled = True
        if not self._memory:
            try:
                with self._connect() as conn:
                    with conn.cursor() as cur:
                        cur.execute(_SCHEMA)
                    conn.commit()
            except Exception:
                self.enabled = False

    def _connect(self) -> Any:
        try:
            import psycopg

            return psycopg.connect(self.dsn)
        except Exception:
            import psycopg2

            return psycopg2.connect(self.dsn)

    def prune(self, *, now: int | None = None) -> None:
        ts = int(time.time()) if now is None else int(now)
        if self._memory:
            bucket, lock = _memory_bucket(self.dsn)
            with lock:
                stale = [jti for jti, exp in bucket.items() if exp < ts]
                for jti in stale:
                    bucket.pop(jti, None)
            return
        if not self.enabled:
            return
        with self._lock, self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM daari_mcp_revoked_jti WHERE exp < %s", (ts,))
            conn.commit()

    def is_revoked(self, jti: str, *, now: int | None = None) -> bool:
        if not jti:
            return False
        self.prune(now=now)
        if self._memory:
            bucket, lock = _memory_bucket(self.dsn)
            with lock:
                return jti in bucket
        if not self.enabled:
            return False
        with self._lock, self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT 1 FROM daari_mcp_revoked_jti WHERE jti = %s",
                    (jti,),
                )
                return cur.fetchone() is not None

    def revoke(self, jti: str, exp: int, *, now: int | None = None) -> None:
        ts = int(time.time()) if now is None else int(now)
        if not jti or int(exp) < ts:
            return
        if self._memory:
            bucket, lock = _memory_bucket(self.dsn)
            with lock:
                bucket[jti] = int(exp)
            self.prune(now=ts)
            return
        if not self.enabled:
            return
        with self._lock, self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO daari_mcp_revoked_jti (jti, exp) VALUES (%s, %s)"
                    " ON CONFLICT (jti) DO UPDATE SET exp = EXCLUDED.exp",
                    (jti, int(exp)),
                )
            conn.commit()
        self.prune(now=ts)

    def clear(self) -> None:
        if self._memory:
            bucket, lock = _memory_bucket(self.dsn)
            with lock:
                bucket.clear()
            return
        if not self.enabled:
            return
        with self._lock, self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM daari_mcp_revoked_jti")
            conn.commit()


class RedisRevokedJtiStore:
    """Shared denylist via Redis keys with EXAT at token exp."""

    def __init__(
        self,
        redis_url: str,
        *,
        prefix: str = "daari:mcp:revoked:",
        timeout_seconds: float = 2.0,
        client: Any | None = None,
    ) -> None:
        self.redis_url = redis_url
        self.prefix = prefix
        self.timeout_seconds = timeout_seconds
        self._client = client
        self.enabled = True
        if client is None:
            try:
                from daari.cache.redis_client import connect_redis

                self._client = connect_redis(redis_url, timeout_seconds=timeout_seconds)
            except Exception:
                self.enabled = False
                self._client = None

    def _key(self, jti: str) -> str:
        return f"{self.prefix}{jti}"

    def prune(self, *, now: int | None = None) -> None:
        # Redis EXAT drops keys; nothing to scan.
        return

    def is_revoked(self, jti: str, *, now: int | None = None) -> bool:
        if not jti or not self.enabled or self._client is None:
            return False
        try:
            return bool(self._client.exists(self._key(jti)))
        except Exception:
            return False

    def revoke(self, jti: str, exp: int, *, now: int | None = None) -> None:
        ts = int(time.time()) if now is None else int(now)
        if not jti or int(exp) < ts or not self.enabled or self._client is None:
            return
        try:
            # EXAT prefers absolute expiry; fall back to TTL seconds.
            key = self._key(jti)
            try:
                self._client.set(key, "1", exat=int(exp))
            except TypeError:
                ttl = max(1, int(exp) - ts)
                self._client.set(key, "1", ex=ttl)
        except Exception:
            return

    def clear(self) -> None:
        if not self.enabled or self._client is None:
            return
        try:
            keys = list(self._client.scan_iter(match=f"{self.prefix}*"))
            if keys:
                self._client.delete(*keys)
        except Exception:
            return


def resolve_revocation_store(settings: Any) -> RevokedJtiStore:
    """Pick Redis (cache.backend=redis), else Postgres URL, else in-process."""
    cache = getattr(settings, "cache", None)
    backend = str(getattr(cache, "backend", "disk") or "disk").strip().lower()
    redis_url = str(getattr(cache, "redis_url", "") or "").strip()
    if backend == "redis" and redis_url:
        timeout = float(getattr(cache, "redis_timeout_seconds", 2.0) or 2.0)
        return RedisRevokedJtiStore(
            redis_url,
            prefix="daari:mcp:revoked:",
            timeout_seconds=timeout,
        )
    obs = getattr(settings, "observability", None)
    pg_url = str(getattr(obs, "postgres_url", "") or "").strip()
    if pg_url:
        return PostgresRevokedJtiStore(pg_url)
    return InProcessRevokedJtiStore()
