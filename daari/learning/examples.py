"""Opt-in training-example capture for local fine-tuning (Phase D2a).

Unlike the D1 FeedbackStore (metadata only), this store keeps full
(prompt messages, completion) pairs — which is why it is off by default
(`learning.capture_examples`) and lives in its own file the user can
inspect and wipe (`daari learn examples --clear`). Same best-effort
contract as the other stores: writes never fail the request path.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_SCHEMA = """
CREATE TABLE IF NOT EXISTS examples (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    trace_id TEXT,
    category TEXT,
    complexity TEXT,
    tier TEXT NOT NULL,
    model TEXT,
    messages_json TEXT NOT NULL,
    completion TEXT NOT NULL,
    accepted INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_examples_trace ON examples(trace_id);
"""


class ExampleStore:
    def __init__(self, path: str | Path, *, enabled: bool = True, max_rows: int = 5000) -> None:
        self.path = Path(path).expanduser()
        self.enabled = enabled
        self.max_rows = max(1, max_rows)
        self._lock = threading.Lock()
        self._ready = False

    def _connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.path, timeout=5.0)
        if not self._ready:
            conn.executescript(_SCHEMA)
            self._ready = True
        return conn

    def record(
        self,
        *,
        trace_id: str | None,
        category: str | None,
        complexity: str | None,
        tier: str,
        model: str | None,
        messages: list[dict[str, Any]],
        completion: str,
    ) -> None:
        if not self.enabled:
            return
        try:
            with self._lock, self._connect() as conn:
                conn.execute(
                    "INSERT INTO examples"
                    " (ts, trace_id, category, complexity, tier, model, messages_json, completion)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        datetime.now(timezone.utc).isoformat(),
                        trace_id,
                        category,
                        complexity,
                        tier,
                        model,
                        json.dumps(messages),
                        completion,
                    ),
                )
                conn.execute(
                    "DELETE FROM examples WHERE seq <= ("
                    " SELECT seq FROM examples ORDER BY seq DESC LIMIT 1 OFFSET ?)",
                    (self.max_rows,),
                )
        except Exception:
            pass

    def mark_accepted(self, trace_id: str) -> bool:
        if not self.enabled:
            return False
        try:
            with self._lock, self._connect() as conn:
                cursor = conn.execute(
                    "UPDATE examples SET accepted = 1 WHERE trace_id = ?", (trace_id,)
                )
                return cursor.rowcount > 0
        except Exception:
            return False

    def delete(self, trace_id: str) -> bool:
        if not self.enabled:
            return False
        try:
            with self._lock, self._connect() as conn:
                cursor = conn.execute("DELETE FROM examples WHERE trace_id = ?", (trace_id,))
                return cursor.rowcount > 0
        except Exception:
            return False

    def examples(self, limit: int = 50, *, only_accepted: bool = False) -> list[dict[str, Any]]:
        if not self.enabled:
            return []
        where = "WHERE accepted = 1" if only_accepted else ""
        try:
            with self._lock, self._connect() as conn:
                rows = conn.execute(
                    "SELECT ts, trace_id, category, complexity, tier, model,"
                    f" messages_json, completion, accepted FROM examples {where}"
                    " ORDER BY seq DESC LIMIT ?",
                    (max(1, limit),),
                ).fetchall()
        except Exception:
            return []
        return [
            {
                "ts": row[0],
                "trace_id": row[1],
                "category": row[2],
                "complexity": row[3],
                "tier": row[4],
                "model": row[5],
                "messages": json.loads(row[6]),
                "completion": row[7],
                "accepted": bool(row[8]),
            }
            for row in rows
        ]

    def count(self, *, only_accepted: bool = False) -> int:
        if not self.enabled:
            return 0
        where = "WHERE accepted = 1" if only_accepted else ""
        try:
            with self._lock, self._connect() as conn:
                return conn.execute(f"SELECT COUNT(*) FROM examples {where}").fetchone()[0]
        except Exception:
            return 0

    def clear(self) -> int:
        if not self.enabled:
            return 0
        try:
            with self._lock, self._connect() as conn:
                cursor = conn.execute("DELETE FROM examples")
                return cursor.rowcount
        except Exception:
            return 0
