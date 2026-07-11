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
    steps TEXT NOT NULL
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
            except Exception:
                self.enabled = False

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path, timeout=5.0)

    def save(self, trace: RequestTrace, *, tier: str | None = None, category: str | None = None) -> None:
        if not self.enabled:
            return
        try:
            with self._lock, self._connect() as conn:
                conn.execute(
                    "INSERT OR REPLACE INTO traces (trace_id, ts, tier, category, steps)"
                    " VALUES (?, ?, ?, ?, ?)",
                    (
                        trace.trace_id,
                        datetime.now(timezone.utc).isoformat(),
                        tier,
                        category,
                        json.dumps(trace.steps),
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
                row = conn.execute(
                    "SELECT trace_id, ts, tier, category, steps FROM traces WHERE trace_id = ?",
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
        }

    def list(self, limit: int = 20) -> list[dict[str, Any]]:
        if not self.enabled:
            return []
        try:
            with self._lock, self._connect() as conn:
                rows = conn.execute(
                    "SELECT trace_id, ts, tier, category FROM traces ORDER BY seq DESC LIMIT ?",
                    (max(1, limit),),
                ).fetchall()
        except Exception:
            return []
        return [
            {"trace_id": row[0], "ts": row[1], "tier": row[2], "category": row[3]}
            for row in rows
        ]
