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
    stored INTEGER NOT NULL
)
"""


class ResponseStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path).expanduser()
        self._lock = threading.Lock()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.execute(_SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path, timeout=5.0)

    def put(
        self,
        response_id: str,
        body: dict[str, Any],
        *,
        conversation: list[dict[str, Any]] | None = None,
        stored: bool = True,
    ) -> None:
        if not stored:
            return
        with self._lock, self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO responses (response_id, body, conversation, stored)"
                " VALUES (?, ?, ?, 1)",
                (
                    response_id,
                    json.dumps(body),
                    json.dumps(conversation or []),
                ),
            )

    def get(self, response_id: str) -> dict[str, Any] | None:
        with self._lock, self._connect() as conn:
            row = conn.execute(
                "SELECT body, conversation FROM responses WHERE response_id = ?",
                (response_id,),
            ).fetchone()
        if row is None:
            return None
        body = json.loads(row[0])
        body["_conversation"] = json.loads(row[1])
        return body
