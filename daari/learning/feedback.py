"""On-device outcome store for the personal feedback loop (Phase D1a).

Stores outcome metadata only — never prompt or completion text. Same
best-effort contract as the usage ledger: storage failures must never
fail the request path.
"""

from __future__ import annotations

import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

VALID_SIGNALS = {"accept", "reject"}

_SCHEMA = """
CREATE TABLE IF NOT EXISTS outcomes (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    trace_id TEXT,
    category TEXT,
    complexity TEXT,
    tier TEXT NOT NULL,
    confidence REAL,
    escalated INTEGER NOT NULL DEFAULT 0,
    latency_ms INTEGER NOT NULL DEFAULT 0,
    signal TEXT
);
CREATE INDEX IF NOT EXISTS idx_outcomes_trace ON outcomes(trace_id);
"""


class FeedbackStore:
    def __init__(self, path: str | Path, *, enabled: bool = True, max_rows: int = 20000) -> None:
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

    def record_outcome(
        self,
        *,
        trace_id: str | None,
        category: str | None,
        complexity: str | None,
        tier: str,
        confidence: float | None,
        escalated: bool,
        latency_ms: int,
    ) -> None:
        if not self.enabled:
            return
        try:
            with self._lock, self._connect() as conn:
                conn.execute(
                    "INSERT INTO outcomes"
                    " (ts, trace_id, category, complexity, tier, confidence, escalated, latency_ms)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        datetime.now(timezone.utc).isoformat(),
                        trace_id,
                        category,
                        complexity,
                        tier,
                        confidence,
                        1 if escalated else 0,
                        int(latency_ms),
                    ),
                )
                conn.execute(
                    "DELETE FROM outcomes WHERE seq <= ("
                    " SELECT seq FROM outcomes ORDER BY seq DESC LIMIT 1 OFFSET ?)",
                    (self.max_rows,),
                )
        except Exception:
            pass

    def record_signal(self, trace_id: str, signal: str) -> bool:
        """Attach explicit accept/reject to an outcome; False if trace unknown."""
        if signal not in VALID_SIGNALS:
            raise ValueError(f"signal must be one of {sorted(VALID_SIGNALS)}")
        if not self.enabled:
            return False
        try:
            with self._lock, self._connect() as conn:
                cursor = conn.execute(
                    "UPDATE outcomes SET signal = ? WHERE trace_id = ?",
                    (signal, trace_id),
                )
                return cursor.rowcount > 0
        except Exception:
            return False

    def outcomes(self, limit: int = 50) -> list[dict[str, Any]]:
        if not self.enabled:
            return []
        try:
            with self._lock, self._connect() as conn:
                rows = conn.execute(
                    "SELECT ts, trace_id, category, complexity, tier, confidence,"
                    " escalated, latency_ms, signal"
                    " FROM outcomes ORDER BY seq DESC LIMIT ?",
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
                "confidence": row[5],
                "escalated": bool(row[6]),
                "latency_ms": row[7],
                "signal": row[8],
            }
            for row in rows
        ]
