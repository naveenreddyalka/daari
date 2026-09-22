"""Postgres-backed Idempotency-Key store for cross-replica fleets (#714).

Duck-types IdempotencyStore. DSN is ``observability.postgres_url``.
``memory:<name>`` is an in-process shared backend for unit tests.
"""

from __future__ import annotations

import threading
import time
from typing import Any

_SCHEMA = """
CREATE TABLE IF NOT EXISTS daari_idempotency (
    principal TEXT NOT NULL,
    idem_key TEXT NOT NULL,
    body_hash TEXT NOT NULL,
    state TEXT NOT NULL,
    status_code INTEGER,
    response_body TEXT,
    media_type TEXT,
    stream INTEGER NOT NULL DEFAULT 0,
    assistant_text TEXT,
    created_at BIGINT NOT NULL,
    PRIMARY KEY (principal, idem_key)
)
"""

_MEMORY: dict[str, dict[tuple[str, str], dict[str, Any]]] = {}
_MEMORY_LOCKS: dict[str, threading.Lock] = {}
_MEMORY_META_LOCK = threading.Lock()


def _memory_bucket(dsn: str) -> tuple[dict[tuple[str, str], dict[str, Any]], threading.Lock]:
    with _MEMORY_META_LOCK:
        if dsn not in _MEMORY:
            _MEMORY[dsn] = {}
            _MEMORY_LOCKS[dsn] = threading.Lock()
        return _MEMORY[dsn], _MEMORY_LOCKS[dsn]


class PostgresIdempotencyStore:
    """Shared idempotency records for multi-replica gateways (#714)."""

    def __init__(self, dsn: str, *, ttl_seconds: int = 86400) -> None:
        self.dsn = dsn
        self.path = dsn
        self.ttl_seconds = max(0, int(ttl_seconds))
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

    def get(self, principal: str, idem_key: str) -> dict[str, Any] | None:
        if self._memory:
            bucket, lock = _memory_bucket(self.dsn)
            with lock:
                row = bucket.get((principal, idem_key))
                return dict(row) if row is not None else None
        if not self.enabled:
            return None
        with self._lock, self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT body_hash, state, status_code, response_body, media_type,"
                    " stream, assistant_text, created_at"
                    " FROM daari_idempotency WHERE principal = %s AND idem_key = %s",
                    (principal, idem_key),
                )
                row = cur.fetchone()
        if row is None:
            return None
        return {
            "body_hash": row[0],
            "state": row[1],
            "status_code": row[2],
            "response_body": row[3],
            "media_type": row[4],
            "stream": bool(row[5]),
            "assistant_text": row[6],
            "created_at": int(row[7] or 0),
        }

    def begin(self, principal: str, idem_key: str, body_hash: str) -> bool:
        now = int(time.time())
        if self._memory:
            bucket, lock = _memory_bucket(self.dsn)
            with lock:
                key = (principal, idem_key)
                if key in bucket:
                    return False
                bucket[key] = {
                    "body_hash": body_hash,
                    "state": "pending",
                    "status_code": None,
                    "response_body": None,
                    "media_type": None,
                    "stream": False,
                    "assistant_text": None,
                    "created_at": now,
                }
                return True
        if not self.enabled:
            return True
        with self._lock, self._connect() as conn:
            with conn.cursor() as cur:
                try:
                    cur.execute(
                        "INSERT INTO daari_idempotency"
                        " (principal, idem_key, body_hash, state, created_at)"
                        " VALUES (%s, %s, %s, 'pending', %s)",
                        (principal, idem_key, body_hash, now),
                    )
                    conn.commit()
                    return True
                except Exception:
                    conn.rollback()
                    return False

    def complete(
        self,
        principal: str,
        idem_key: str,
        *,
        status_code: int,
        response_body: str,
        media_type: str,
        stream: bool = False,
        assistant_text: str | None = None,
    ) -> None:
        now = int(time.time())
        if self._memory:
            bucket, lock = _memory_bucket(self.dsn)
            with lock:
                row = bucket.get((principal, idem_key))
                if row is None:
                    return
                row.update(
                    {
                        "state": "complete",
                        "status_code": int(status_code),
                        "response_body": response_body,
                        "media_type": media_type,
                        "stream": bool(stream),
                        "assistant_text": assistant_text,
                        "created_at": now,
                    }
                )
            return
        if not self.enabled:
            return
        with self._lock, self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE daari_idempotency SET state = 'complete', status_code = %s,"
                    " response_body = %s, media_type = %s, stream = %s, assistant_text = %s,"
                    " created_at = %s"
                    " WHERE principal = %s AND idem_key = %s",
                    (
                        int(status_code),
                        response_body,
                        media_type,
                        1 if stream else 0,
                        assistant_text,
                        now,
                        principal,
                        idem_key,
                    ),
                )
            conn.commit()

    def abandon(self, principal: str, idem_key: str) -> None:
        if self._memory:
            bucket, lock = _memory_bucket(self.dsn)
            with lock:
                key = (principal, idem_key)
                row = bucket.get(key)
                if row is not None and row.get("state") == "pending":
                    del bucket[key]
            return
        if not self.enabled:
            return
        with self._lock, self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM daari_idempotency WHERE principal = %s AND idem_key = %s"
                    " AND state = 'pending'",
                    (principal, idem_key),
                )
            conn.commit()

    def prune_older_than(self, cutoff_epoch: float, *, dry_run: bool = False) -> int:
        cutoff = int(cutoff_epoch)
        if self._memory:
            bucket, lock = _memory_bucket(self.dsn)
            with lock:
                doomed = [
                    key
                    for key, row in bucket.items()
                    if int(row.get("created_at") or 0) > 0
                    and int(row["created_at"]) <= cutoff
                ]
                if dry_run:
                    return len(doomed)
                for key in doomed:
                    del bucket[key]
                return len(doomed)
        if not self.enabled:
            return 0
        with self._lock, self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT COUNT(*) FROM daari_idempotency"
                    " WHERE created_at > 0 AND created_at <= %s",
                    (cutoff,),
                )
                count = int(cur.fetchone()[0] or 0)
                if dry_run or count == 0:
                    return count
                cur.execute(
                    "DELETE FROM daari_idempotency"
                    " WHERE created_at > 0 AND created_at <= %s",
                    (cutoff,),
                )
            conn.commit()
            return count
