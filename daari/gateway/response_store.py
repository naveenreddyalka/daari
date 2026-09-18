"""Persist Responses API objects for GET, previous_response_id, and background (#165, #497)."""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

_SCHEMA = """
CREATE TABLE IF NOT EXISTS responses (
    response_id TEXT PRIMARY KEY,
    body TEXT NOT NULL,
    conversation TEXT NOT NULL,
    stored INTEGER NOT NULL,
    owner_key_id TEXT,
    created_at INTEGER NOT NULL DEFAULT 0
)
"""


def response_visible_to_caller(stored: dict[str, Any], claims: Any | None) -> bool:
    """Return whether auth claims may see this stored response (#453).

    Master / no-auth sees everything. Virtual keys see only responses they own;
    pre-migration ownerless rows stay master-only.
    """
    kind = getattr(claims, "kind", None) if claims is not None else None
    if kind != "virtual":
        return True
    owner = stored.get("_owner_key_id")
    if not owner:
        return False
    return owner == getattr(claims, "key_id", None)


class ResponseStore:
    def __init__(self, path: str | Path, *, retention_days: int = 0) -> None:
        self.path = Path(path).expanduser()
        self.retention_days = max(0, int(retention_days))
        self._lock = threading.Lock()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.execute(_SCHEMA)
            self._migrate(conn)

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path, timeout=5.0)

    @staticmethod
    def _migrate(conn: sqlite3.Connection) -> None:
        cols = {row[1] for row in conn.execute("PRAGMA table_info(responses)")}
        if "owner_key_id" not in cols:
            conn.execute("ALTER TABLE responses ADD COLUMN owner_key_id TEXT")
        if "created_at" not in cols:
            conn.execute(
                "ALTER TABLE responses ADD COLUMN created_at INTEGER NOT NULL DEFAULT 0"
            )
            # Best-effort backfill from JSON body.created_at when present.
            rows = conn.execute("SELECT response_id, body FROM responses").fetchall()
            for response_id, body_raw in rows:
                stamp = 0
                try:
                    stamp = int(json.loads(body_raw).get("created_at") or 0)
                except (TypeError, ValueError, json.JSONDecodeError):
                    stamp = 0
                if stamp <= 0:
                    stamp = int(time.time())
                conn.execute(
                    "UPDATE responses SET created_at = ? WHERE response_id = ?",
                    (stamp, response_id),
                )

    def put(
        self,
        response_id: str,
        body: dict[str, Any],
        *,
        conversation: list[dict[str, Any]] | None = None,
        stored: bool = True,
        owner_key_id: str | None = None,
    ) -> None:
        if not stored:
            return
        now = int(time.time())
        with self._lock, self._connect() as conn:
            existing = conn.execute(
                "SELECT owner_key_id, created_at FROM responses WHERE response_id = ?",
                (response_id,),
            ).fetchone()
            created_at = now
            # Background/queued updates omit owner; keep the create-time owner (#453).
            if existing is not None:
                if owner_key_id is None:
                    owner_key_id = existing[0]
                if existing[1]:
                    created_at = int(existing[1])
            conn.execute(
                "INSERT OR REPLACE INTO responses"
                " (response_id, body, conversation, stored, owner_key_id, created_at)"
                " VALUES (?, ?, ?, 1, ?, ?)",
                (
                    response_id,
                    json.dumps(body),
                    json.dumps(conversation or []),
                    owner_key_id,
                    created_at,
                ),
            )

    def get(self, response_id: str) -> dict[str, Any] | None:
        with self._lock, self._connect() as conn:
            row = conn.execute(
                "SELECT body, conversation, owner_key_id FROM responses"
                " WHERE response_id = ?",
                (response_id,),
            ).fetchone()
        if row is None:
            return None
        body = json.loads(row[0])
        body["_conversation"] = json.loads(row[1])
        body["_owner_key_id"] = row[2]
        return body

    def delete(self, response_id: str) -> bool:
        with self._lock, self._connect() as conn:
            cursor = conn.execute(
                "DELETE FROM responses WHERE response_id = ?",
                (response_id,),
            )
            return cursor.rowcount > 0

    def prune_older_than(self, cutoff_epoch: float, *, dry_run: bool = False) -> int:
        """Delete (or count) responses with created_at <= cutoff (#497)."""
        cutoff = int(cutoff_epoch)
        with self._lock, self._connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) FROM responses WHERE created_at > 0 AND created_at <= ?",
                (cutoff,),
            ).fetchone()
            count = int(row[0] if row else 0)
            if dry_run or count == 0:
                return count
            conn.execute(
                "DELETE FROM responses WHERE created_at > 0 AND created_at <= ?",
                (cutoff,),
            )
            return count
