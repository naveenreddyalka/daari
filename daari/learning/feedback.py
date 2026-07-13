"""On-device outcome store for the personal feedback loop (Phase D1a).

Stores outcome metadata only — never prompt or completion text. Same
best-effort contract as the usage ledger: storage failures must never
fail the request path.
"""

from __future__ import annotations

import sqlite3
import threading
from datetime import datetime, timedelta, timezone
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
CREATE TABLE IF NOT EXISTS shadow_checks (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    category TEXT,
    similarity REAL,
    agreed INTEGER NOT NULL
);
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

    def stats(self, days: int = 7) -> dict[str, dict[str, dict[str, Any]]]:
        """Per (category, tier) outcome evidence for the learning loop."""
        if not self.enabled:
            return {}
        cutoff = (datetime.now(timezone.utc) - timedelta(days=max(0, days))).isoformat()
        try:
            with self._lock, self._connect() as conn:
                rows = conn.execute(
                    "SELECT category, tier, COUNT(*), SUM(escalated),"
                    " SUM(CASE WHEN signal = 'accept' THEN 1 ELSE 0 END),"
                    " SUM(CASE WHEN signal = 'reject' THEN 1 ELSE 0 END),"
                    " AVG(confidence), AVG(latency_ms)"
                    " FROM outcomes WHERE ts >= ?"
                    " GROUP BY category, tier",
                    (cutoff,),
                ).fetchall()
        except Exception:
            return {}
        stats: dict[str, dict[str, dict[str, Any]]] = {}
        for category, tier, outcomes, escalated, accepts, rejects, avg_conf, avg_latency in rows:
            entry = {
                "outcomes": outcomes,
                "escalated": escalated or 0,
                "escalation_rate": round((escalated or 0) / outcomes, 4) if outcomes else 0.0,
                "accepts": accepts or 0,
                "rejects": rejects or 0,
                "reject_rate": round((rejects or 0) / outcomes, 4) if outcomes else 0.0,
                "avg_confidence": round(avg_conf, 4) if avg_conf is not None else None,
                "avg_latency_ms": round(avg_latency, 1) if avg_latency is not None else None,
            }
            stats.setdefault(category or "unknown", {})[tier] = entry
        return stats

    def record_shadow(self, *, category: str | None, similarity: float, agreed: bool) -> None:
        """Trust PRD T1c: outcome of comparing an L1 hit with a fresh answer."""
        if not self.enabled:
            return
        try:
            with self._lock, self._connect() as conn:
                conn.execute(
                    "INSERT INTO shadow_checks (ts, category, similarity, agreed)"
                    " VALUES (?, ?, ?, ?)",
                    (
                        datetime.now(timezone.utc).isoformat(),
                        category,
                        float(similarity),
                        1 if agreed else 0,
                    ),
                )
        except Exception:
            pass

    def shadow_stats(self, days: int = 7) -> dict[str, dict[str, Any]]:
        """Per-category false-hit rate from shadow sampling."""
        if not self.enabled:
            return {}
        cutoff = (datetime.now(timezone.utc) - timedelta(days=max(0, days))).isoformat()
        try:
            with self._lock, self._connect() as conn:
                rows = conn.execute(
                    "SELECT category, COUNT(*),"
                    " SUM(CASE WHEN agreed = 0 THEN 1 ELSE 0 END), AVG(similarity)"
                    " FROM shadow_checks WHERE ts >= ? GROUP BY category",
                    (cutoff,),
                ).fetchall()
        except Exception:
            return {}
        return {
            (category or "unknown"): {
                "samples": samples,
                "disagreements": disagreements or 0,
                "false_hit_rate": round((disagreements or 0) / samples, 4) if samples else 0.0,
                "avg_answer_similarity": round(avg_sim, 4) if avg_sim is not None else None,
            }
            for category, samples, disagreements, avg_sim in rows
        }

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
