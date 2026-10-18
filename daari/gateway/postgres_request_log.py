"""Postgres-backed gateway request/event log for fleets (#1631).

DSN is ``observability.postgres_url``. ``memory:<name>`` shares rows across
instances for unit tests. Writes are best-effort (never raise into callers).
"""

from __future__ import annotations

import json
import threading
from datetime import UTC, datetime
from typing import Any

# Shipped schema marker for ``daari migrate`` / doctor (#1655).
SCHEMA_VERSION = 1

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

    def query_events(
        self,
        *,
        limit: int = 100,
        offset: int = 0,
        before_id: int | None = None,
        team_id: str | None = None,
        key_id: str | None = None,
        kind: str | None = None,
    ) -> tuple[list[dict[str, Any]], int]:
        """Newest-first page plus total matches (#1683).

        ``before_id`` keeps rows with ``id`` strictly less than that cursor.
        ``team_id`` / ``key_id`` match those payload fields when set.
        ``kind`` matches the event name (case-insensitive).
        """
        lim = max(1, min(int(limit), 1000))
        off = max(0, int(offset))
        team = (team_id or "").strip() or None
        key = (key_id or "").strip() or None
        kind_norm = (kind or "").strip().lower() or None
        if self._memory:
            rows, lock = _memory_bucket(self.dsn)
            with lock:
                matched = [
                    dict(r)
                    for r in rows
                    if _row_in_query(
                        r,
                        before_id=before_id,
                        team_id=team,
                        key_id=key,
                        kind=kind_norm,
                    )
                ]
            matched.sort(key=lambda r: int(r["id"]), reverse=True)
            return matched[off : off + lim], len(matched)
        if not self.enabled:
            return [], 0
        clauses: list[str] = []
        params: list[Any] = []
        if before_id is not None:
            clauses.append("id < %s")
            params.append(int(before_id))
        if team is not None:
            clauses.append("(payload::json->>'team_id') = %s")
            params.append(team)
        if key is not None:
            clauses.append("(payload::json->>'key_id') = %s")
            params.append(key)
        if kind_norm is not None:
            clauses.append("lower(event) = %s")
            params.append(kind_norm)
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        with self._lock, self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"SELECT COUNT(*) FROM daari_request_log{where}",
                    params,
                )
                total = int(cur.fetchone()[0] or 0)
                cur.execute(
                    "SELECT id, ts, event, payload FROM daari_request_log"
                    f"{where} ORDER BY id DESC LIMIT %s OFFSET %s",
                    [*params, lim, off],
                )
                fetched = cur.fetchall()
        return [_decode_row(row) for row in fetched], total

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
        return [_decode_row(row) for row in fetched]

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

    def erase_subject(
        self,
        *,
        kind: str,
        value: str,
        dry_run: bool = False,
    ) -> int:
        """Delete rows whose payload mentions the subject (#1651)."""
        needle = (value or "").strip()
        kind_norm = (kind or "").strip().lower()
        if not needle or kind_norm not in {"key", "team", "user"}:
            return 0
        if self._memory:
            rows, lock = _memory_bucket(self.dsn)
            with lock:
                keep: list[dict[str, Any]] = []
                removed = 0
                for r in rows:
                    payload = r.get("payload") if isinstance(r.get("payload"), dict) else {}
                    if _payload_matches_subject(payload, kind_norm, needle):
                        removed += 1
                    else:
                        keep.append(r)
                if dry_run or removed == 0:
                    return removed
                rows[:] = keep
                return removed
        if not self.enabled:
            return 0
        try:
            with self._lock, self._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT id, payload FROM daari_request_log ORDER BY id ASC"
                    )
                    doomed: list[int] = []
                    for row_id, raw_payload in cur.fetchall():
                        payload = raw_payload
                        if isinstance(payload, str):
                            try:
                                payload = json.loads(payload)
                            except json.JSONDecodeError:
                                payload = {}
                        if not isinstance(payload, dict):
                            continue
                        if _payload_matches_subject(payload, kind_norm, needle):
                            doomed.append(int(row_id))
                    if dry_run or not doomed:
                        return len(doomed)
                    cur.executemany(
                        "DELETE FROM daari_request_log WHERE id = %s",
                        [(i,) for i in doomed],
                    )
                conn.commit()
                return len(doomed)
        except Exception:
            return 0


def _decode_row(row: Any) -> dict[str, Any]:
    payload = row[3]
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except json.JSONDecodeError:
            payload = {"raw": payload}
    return {
        "id": int(row[0]),
        "ts": row[1],
        "event": row[2],
        "payload": payload if isinstance(payload, dict) else {"raw": payload},
    }


def _row_in_query(
    row: dict[str, Any],
    *,
    before_id: int | None,
    team_id: str | None,
    key_id: str | None,
    kind: str | None = None,
) -> bool:
    if before_id is not None and int(row.get("id") or 0) >= int(before_id):
        return False
    payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}
    if team_id is not None and str(payload.get("team_id") or "") != team_id:
        return False
    if key_id is not None and str(payload.get("key_id") or "") != key_id:
        return False
    if kind is not None and str(row.get("event") or "").strip().lower() != kind:
        return False
    return True


def _payload_matches_subject(payload: dict[str, Any], kind: str, value: str) -> bool:
    """Same subject rules as JSONL request-log erase (#1130 / #1651)."""
    if kind == "key":
        for field in ("key_id", "owner_key_id"):
            if str(payload.get(field) or "") == value:
                return True
        principal = payload.get("principal")
        if isinstance(principal, str) and (
            principal == value or principal == f"vk:{value}"
        ):
            return True
        return False
    if kind == "team":
        return str(payload.get("team_id") or "") == value
    for field in ("user", "user_id", "client_id", "client"):
        if str(payload.get(field) or "") == value:
            return True
    return False


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
