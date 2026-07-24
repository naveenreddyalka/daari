"""Postgres-backed request traces for stateless gateway replicas (issue #116)."""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from typing import Any

from daari.observability.trace import RequestTrace

_SCHEMA = """
CREATE TABLE IF NOT EXISTS traces (
    seq BIGSERIAL PRIMARY KEY,
    trace_id TEXT NOT NULL UNIQUE,
    ts TEXT NOT NULL,
    tier TEXT,
    category TEXT,
    steps TEXT NOT NULL
);
"""


class PostgresTraceStore:
    def __init__(self, dsn: str, enabled: bool = True, max_entries: int = 200) -> None:
        self.dsn = dsn
        self.enabled = enabled
        self.max_entries = max(1, max_entries)
        self.path = dsn
        self._lock = threading.Lock()
        if self.enabled:
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
        except ImportError as exc:
            raise RuntimeError(
                "observability.backend=postgres requires psycopg — "
                "pip install 'psycopg[binary]>=3' (or daari[postgres])"
            ) from exc
        return psycopg.connect(self.dsn)

    def save(
        self, trace: RequestTrace, *, tier: str | None = None, category: str | None = None
    ) -> None:
        if not self.enabled:
            return
        try:
            with self._lock, self._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO traces (trace_id, ts, tier, category, steps)
                        VALUES (%s, %s, %s, %s, %s)
                        ON CONFLICT (trace_id) DO UPDATE SET
                            ts = EXCLUDED.ts,
                            tier = EXCLUDED.tier,
                            category = EXCLUDED.category,
                            steps = EXCLUDED.steps
                        """,
                        (
                            trace.trace_id,
                            datetime.now(timezone.utc).isoformat(),
                            tier,
                            category,
                            json.dumps(trace.steps),
                        ),
                    )
                    cur.execute(
                        "DELETE FROM traces WHERE seq NOT IN"
                        " (SELECT seq FROM traces ORDER BY seq DESC LIMIT %s)",
                        (self.max_entries,),
                    )
                conn.commit()
        except Exception:
            pass

    def get(self, trace_id: str) -> dict[str, Any] | None:
        if not self.enabled:
            return None
        try:
            with self._lock, self._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT trace_id, ts, tier, category, steps FROM traces"
                        " WHERE trace_id = %s",
                        (trace_id,),
                    )
                    row = cur.fetchone()
            if row is None:
                return None
            return {
                "trace_id": row[0],
                "ts": row[1],
                "tier": row[2],
                "category": row[3],
                "steps": json.loads(row[4]),
            }
        except Exception:
            return None

    def list(self, limit: int = 50) -> list[dict[str, Any]]:
        if not self.enabled:
            return []
        try:
            with self._lock, self._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT trace_id, ts, tier, category, steps FROM traces"
                        " ORDER BY seq DESC LIMIT %s",
                        (max(1, limit),),
                    )
                    rows = cur.fetchall()
            return [
                {
                    "trace_id": row[0],
                    "ts": row[1],
                    "tier": row[2],
                    "category": row[3],
                    "steps": json.loads(row[4]),
                }
                for row in rows
            ]
        except Exception:
            return []
