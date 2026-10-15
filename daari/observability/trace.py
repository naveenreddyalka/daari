"""Per-request decision traces: what daari did for each prompt.

A RequestTrace accumulates ordered steps (cache lookups, policy decisions,
tier attempts, escalations); TraceStore persists the most recent N so they
can be shown to a user or their client after the fact. The active trace
travels via a contextvar so instrumentation points don't need signature
changes. Everything is best-effort: tracing must never fail a request.
"""

from __future__ import annotations

import contextvars
import json
import sqlite3
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_SCHEMA = """
CREATE TABLE IF NOT EXISTS traces (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    trace_id TEXT NOT NULL UNIQUE,
    ts TEXT NOT NULL,
    tier TEXT,
    category TEXT,
    steps TEXT NOT NULL,
    team_id TEXT NOT NULL DEFAULT ''
)
"""


class RequestTrace:
    def __init__(self, trace_id: str | None = None) -> None:
        self.trace_id = trace_id or uuid.uuid4().hex[:16]
        self._started = time.perf_counter()
        self.steps: list[dict[str, Any]] = []

    def add(self, step: str, **detail: Any) -> None:
        entry: dict[str, Any] = {
            "step": step,
            "elapsed_ms": int((time.perf_counter() - self._started) * 1000),
        }
        if detail:
            entry["detail"] = detail
        self.steps.append(entry)


_current: contextvars.ContextVar[RequestTrace | None] = contextvars.ContextVar(
    "daari_request_trace", default=None
)


def start_trace() -> RequestTrace:
    trace = RequestTrace()
    _current.set(trace)
    return trace


def current_trace() -> RequestTrace | None:
    return _current.get()


def add_step(step: str, **detail: Any) -> None:
    trace = _current.get()
    if trace is not None:
        trace.add(step, **detail)


def end_trace() -> None:
    _current.set(None)


class TraceStore:
    def __init__(self, path: str | Path, enabled: bool = True, max_entries: int = 200) -> None:
        self.path = Path(path).expanduser()
        self.enabled = enabled
        self.max_entries = max(1, max_entries)
        self._lock = threading.Lock()
        if self.enabled:
            try:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                with self._connect() as conn:
                    conn.execute(_SCHEMA)
                    self._ensure_team_column(conn)
            except Exception:
                self.enabled = False

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path, timeout=5.0)

    @staticmethod
    def _ensure_team_column(conn: sqlite3.Connection) -> None:
        cols = {row[1] for row in conn.execute("PRAGMA table_info(traces)").fetchall()}
        if "team_id" not in cols:
            conn.execute(
                "ALTER TABLE traces ADD COLUMN team_id TEXT NOT NULL DEFAULT ''"
            )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_traces_team ON traces (team_id)"
        )

    def save(
        self,
        trace: RequestTrace,
        *,
        tier: str | None = None,
        category: str | None = None,
        team_id: str | None = None,
    ) -> None:
        if not self.enabled:
            return
        try:
            with self._lock, self._connect() as conn:
                self._ensure_team_column(conn)
                conn.execute(
                    "INSERT OR REPLACE INTO traces"
                    " (trace_id, ts, tier, category, steps, team_id)"
                    " VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        trace.trace_id,
                        datetime.now(timezone.utc).isoformat(),
                        tier,
                        category,
                        json.dumps(trace.steps),
                        (team_id or "").strip(),
                    ),
                )
                conn.execute(
                    "DELETE FROM traces WHERE seq NOT IN"
                    " (SELECT seq FROM traces ORDER BY seq DESC LIMIT ?)",
                    (self.max_entries,),
                )
        except Exception:
            pass

    def get(self, trace_id: str) -> dict[str, Any] | None:
        if not self.enabled:
            return None
        try:
            with self._lock, self._connect() as conn:
                self._ensure_team_column(conn)
                row = conn.execute(
                    "SELECT trace_id, ts, tier, category, steps, team_id"
                    " FROM traces WHERE trace_id = ?",
                    (trace_id,),
                ).fetchone()
        except Exception:
            return None
        if row is None:
            return None
        return {
            "trace_id": row[0],
            "ts": row[1],
            "tier": row[2],
            "category": row[3],
            "steps": json.loads(row[4]),
            "team_id": row[5] or "",
        }

    def list(self, limit: int = 20, *, team_id: str | None = None) -> list[dict[str, Any]]:
        if not self.enabled:
            return []
        try:
            with self._lock, self._connect() as conn:
                self._ensure_team_column(conn)
                wanted = (team_id or "").strip()
                if wanted:
                    rows = conn.execute(
                        "SELECT trace_id, ts, tier, category, team_id FROM traces"
                        " WHERE team_id = ? ORDER BY seq DESC LIMIT ?",
                        (wanted, max(1, limit)),
                    ).fetchall()
                else:
                    rows = conn.execute(
                        "SELECT trace_id, ts, tier, category, team_id FROM traces"
                        " ORDER BY seq DESC LIMIT ?",
                        (max(1, limit),),
                    ).fetchall()
        except Exception:
            return []
        return [
            {
                "trace_id": row[0],
                "ts": row[1],
                "tier": row[2],
                "category": row[3],
                "team_id": row[4] or "",
            }
            for row in rows
        ]

    def prune_before(self, cutoff: str, *, dry_run: bool = False) -> int:
        if not self.enabled:
            return 0
        try:
            with self._lock, self._connect() as conn:
                count = conn.execute(
                    "SELECT COUNT(*) FROM traces WHERE ts < ?", (cutoff,)
                ).fetchone()[0]
                if not dry_run and count:
                    conn.execute("DELETE FROM traces WHERE ts < ?", (cutoff,))
                return int(count)
        except Exception:
            return 0

    def erase_subject(
        self,
        *,
        kind: str,
        value: str,
        dry_run: bool = False,
    ) -> int:
        """Delete traces whose steps JSON mention the subject id (#1170)."""
        needle = (value or "").strip()
        if not self.enabled or not needle:
            return 0
        try:
            with self._lock, self._connect() as conn:
                rows = conn.execute(
                    "SELECT seq, steps FROM traces WHERE steps LIKE ?",
                    (f"%{needle}%",),
                ).fetchall()
                doomed = [seq for seq, _ in rows]
                if dry_run or not doomed:
                    return len(doomed)
                conn.executemany(
                    "DELETE FROM traces WHERE seq = ?",
                    [(seq,) for seq in doomed],
                )
                return len(doomed)
        except Exception:
            return 0
