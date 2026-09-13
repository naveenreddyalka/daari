"""Persist Responses API objects for GET, previous_response_id, and background (#165)."""

from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any

_SCHEMA = """
CREATE TABLE IF NOT EXISTS responses (
    response_id TEXT PRIMARY KEY,
    body TEXT NOT NULL,
    conversation TEXT NOT NULL,
    stored INTEGER NOT NULL,
    owner_key_id TEXT
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
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path).expanduser()
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
        with self._lock, self._connect() as conn:
            existing = conn.execute(
                "SELECT owner_key_id FROM responses WHERE response_id = ?",
                (response_id,),
            ).fetchone()
            # Background/queued updates omit owner; keep the create-time owner (#453).
            if existing is not None and owner_key_id is None:
                owner_key_id = existing[0]
            conn.execute(
                "INSERT OR REPLACE INTO responses"
                " (response_id, body, conversation, stored, owner_key_id)"
                " VALUES (?, ?, ?, 1, ?)",
                (
                    response_id,
                    json.dumps(body),
                    json.dumps(conversation or []),
                    owner_key_id,
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
