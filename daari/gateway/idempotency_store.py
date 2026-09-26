"""SQLite store for Idempotency-Key replay (#714)."""

from __future__ import annotations

import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

_SCHEMA = """
CREATE TABLE IF NOT EXISTS idempotency (
    principal TEXT NOT NULL,
    idem_key TEXT NOT NULL,
    body_hash TEXT NOT NULL,
    state TEXT NOT NULL,
    status_code INTEGER,
    response_body TEXT,
    media_type TEXT,
    stream INTEGER NOT NULL DEFAULT 0,
    assistant_text TEXT,
    created_at INTEGER NOT NULL,
    PRIMARY KEY (principal, idem_key)
)
"""


class IdempotencyStore:
    """Persist completed (and in-flight) idempotent gateway responses."""

    def __init__(self, path: str | Path, *, ttl_seconds: int = 86400) -> None:
        self.path = Path(path).expanduser()
        self.ttl_seconds = max(0, int(ttl_seconds))
        self._lock = threading.Lock()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.execute(_SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path, timeout=5.0)

    def get(self, principal: str, idem_key: str) -> dict[str, Any] | None:
        with self._lock, self._connect() as conn:
            row = conn.execute(
                "SELECT body_hash, state, status_code, response_body, media_type,"
                " stream, assistant_text, created_at"
                " FROM idempotency WHERE principal = ? AND idem_key = ?",
                (principal, idem_key),
            ).fetchone()
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
        """Insert a pending row. Returns False if the key already exists."""
        now = int(time.time())
        with self._lock, self._connect() as conn:
            try:
                conn.execute(
                    "INSERT INTO idempotency"
                    " (principal, idem_key, body_hash, state, created_at)"
                    " VALUES (?, ?, ?, 'pending', ?)",
                    (principal, idem_key, body_hash, now),
                )
                return True
            except sqlite3.IntegrityError:
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
        with self._lock, self._connect() as conn:
            conn.execute(
                "UPDATE idempotency SET state = 'complete', status_code = ?,"
                " response_body = ?, media_type = ?, stream = ?, assistant_text = ?,"
                " created_at = ?"
                " WHERE principal = ? AND idem_key = ?",
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

    def abandon(self, principal: str, idem_key: str) -> None:
        """Drop a pending row so a retry can claim the key."""
        with self._lock, self._connect() as conn:
            conn.execute(
                "DELETE FROM idempotency WHERE principal = ? AND idem_key = ?"
                " AND state = 'pending'",
                (principal, idem_key),
            )

    def prune_older_than(self, cutoff_epoch: float, *, dry_run: bool = False) -> int:
        cutoff = int(cutoff_epoch)
        with self._lock, self._connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) FROM idempotency WHERE created_at > 0 AND created_at <= ?",
                (cutoff,),
            ).fetchone()
            count = int(row[0] if row else 0)
            if dry_run or count == 0:
                return count
            conn.execute(
                "DELETE FROM idempotency WHERE created_at > 0 AND created_at <= ?",
                (cutoff,),
            )
            return count

    def erase_principals(self, principals: list[str], *, dry_run: bool = False) -> int:
        """Delete idempotency rows for any of ``principals`` (#1130)."""
        ids = [str(p).strip() for p in principals if str(p).strip()]
        if not ids:
            return 0
        placeholders = ",".join("?" for _ in ids)
        with self._lock, self._connect() as conn:
            row = conn.execute(
                f"SELECT COUNT(*) FROM idempotency WHERE principal IN ({placeholders})",
                ids,
            ).fetchone()
            count = int(row[0] if row else 0)
            if dry_run or count == 0:
                return count
            conn.execute(
                f"DELETE FROM idempotency WHERE principal IN ({placeholders})",
                ids,
            )
            return count
