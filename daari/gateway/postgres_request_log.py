"""Postgres-backed gateway request/event log for fleets (#1631).

DSN is ``observability.postgres_url``. ``memory:<name>`` shares rows across
instances for unit tests. Writes are best-effort (never raise into callers).
"""

from __future__ import annotations

import json
import threading
from datetime import UTC, datetime
from typing import Any

_SCHEMA = """
CREATE TABLE IF NOT EXISTS daari_request_log (
    id BIGSERIAL PRIMARY KEY,
    ts TEXT NOT NULL,
    event TEXT NOT NULL,
    payload TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS daari_request_log_ts_idx ON daari_request_log (ts);
"""

_MEMORY: dict[str, list[dict[str, Any]]] = {}
_MEMORY_LOCKS: dict[str, threading.Lock] = {}
_MEMORY_META = threading.Lock()


def _memory_bucket(dsn: str) -> tuple[list[dict[str, Any]], threading.Lock]:
    with _MEMORY_META:
        if dsn not in _MEMORY:
            _MEMORY[dsn] = []
            _MEMORY_LOCKS[dsn] = threading.Lock()
        return _MEMORY[dsn], _MEMORY_LOCKS[dsn]


class PostgresRequestLogStore:
    """Fleet-shared append-only gateway request log (#1631)."""

    def __init__(self, dsn: str, *, enabled: bool = True) -> None:
        self.dsn = dsn
        self.path = dsn
        self.enabled = enabled
        self._lock = threading.Lock()
        self._memory = dsn.startswith("memory:")
        if self.enabled and not self._memory:
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
                "observability.request_log.backend=postgres requires psycopg — "
                "pip install 'psycopg[binary]>=3' (or daari[postgres])"
            ) from exc
        return psycopg.connect(self.dsn)

    def append(
        self,
        event: str,
        payload: dict[str, Any],
        *,
        ts: str | None = None,
    ) -> None:
        """Insert one event. Best-effort: swallows all errors."""
        if not self.enabled:
            return
        body = dict(payload)
        stamp = ts or body.pop("ts", None) or datetime.now(UTC).isoformat()
        body.pop("ts", None)
        try:
            payload_s = json.dumps(body, default=str)
            if self._memory:
                rows, lock = _memory_bucket(self.dsn)
                with lock:
                    next_id = (rows[-1]["id"] + 1) if rows else 1
                    rows.append(
                        {
                            "id": next_id,
                            "ts": stamp,
                            "event": event,
                            "payload": body,
                        }
                    )
                return
            with self._lock, self._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "INSERT INTO daari_request_log (ts, event, payload)"
                        " VALUES (%s, %s, %s)",
                        (stamp, event, payload_s),
                    )
                conn.commit()
        except Exception:
            pass

    def list_events(self, *, limit: int = 1000) -> list[dict[str, Any]]:
        """Return recent rows oldest-first (tests / tooling)."""
        if self._memory:
            rows, lock = _memory_bucket(self.dsn)
            with lock:
                return [dict(r) for r in rows[-limit:]]
        if not self.enabled:
            return []
        with self._lock, self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id, ts, event, payload FROM daari_request_log"
                    " ORDER BY id ASC LIMIT %s",
                    (limit,),
                )
                fetched = cur.fetchall()
        out: list[dict[str, Any]] = []
        for row in fetched:
            payload = row[3]
            if isinstance(payload, str):
                try:
                    payload = json.loads(payload)
                except json.JSONDecodeError:
                    payload = {"raw": payload}
            out.append(
                {
                    "id": int(row[0]),
                    "ts": row[1],
                    "event": row[2],
                    "payload": payload if isinstance(payload, dict) else {"raw": payload},
                }
            )
        return out

    def prune_before(self, cutoff: datetime, *, dry_run: bool = False) -> int:
        """Delete rows with ts strictly before cutoff. Returns count removed."""
        if cutoff.tzinfo is None:
            cutoff = cutoff.replace(tzinfo=UTC)
        cutoff = cutoff.astimezone(UTC)
        cutoff_s = cutoff.isoformat()
        if self._memory:
            rows, lock = _memory_bucket(self.dsn)
            with lock:
                keep: list[dict[str, Any]] = []
                removed = 0
                for r in rows:
                    stamped = _parse_ts(r.get("ts"))
                    if stamped is not None and stamped < cutoff:
                        removed += 1
                    else:
                        keep.append(r)
                if dry_run:
                    return removed
                rows[:] = keep
                return removed
        if not self.enabled:
            return 0
        try:
            with self._lock, self._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT COUNT(*) FROM daari_request_log WHERE ts < %s",
                        (cutoff_s,),
                    )
                    count = int(cur.fetchone()[0] or 0)
                    if dry_run or count == 0:
                        return count
                    cur.execute(
                        "DELETE FROM daari_request_log WHERE ts < %s",
                        (cutoff_s,),
                    )
                conn.commit()
                return count
        except Exception:
            return 0


def _parse_ts(raw: Any) -> datetime | None:
    if not isinstance(raw, str):
        return None
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def request_log_store_from_settings(settings: Any) -> PostgresRequestLogStore | None:
    """Return a postgres store when ``observability.request_log.backend=postgres``."""
    obs = getattr(settings, "observability", None)
    if obs is None:
        return None
    rl = getattr(obs, "request_log", None)
    backend = getattr(rl, "backend", "jsonl") if rl is not None else "jsonl"
    if (backend or "jsonl").strip().lower() != "postgres":
        return None
    dsn = (getattr(obs, "postgres_url", "") or "").strip()
    if not dsn:
        return None
    return PostgresRequestLogStore(dsn)
