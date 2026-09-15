"""Postgres-backed audit log for cross-replica fleets (issue #483).

Single serialized hash chain (pg_advisory_xact_lock / process lock for
``memory:``). Duck-types ``AuditLog``. DSN is ``observability.postgres_url``.
``memory:<name>`` shares rows across instances for unit tests.
"""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from typing import Any, Iterator

from daari.enterprise.audit import (
    GENESIS_HASH,
    VerifyResult,
    _row_dict,
    compute_row_hash,
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS daari_audit (
    seq BIGSERIAL PRIMARY KEY,
    ts TEXT NOT NULL,
    actor TEXT NOT NULL,
    role TEXT NOT NULL,
    action TEXT NOT NULL,
    detail TEXT NOT NULL,
    prev_hash TEXT,
    row_hash TEXT
);
"""

# Advisory lock key namespace for serializing chain appends.
_AUDIT_LOCK_KEY = 748_301_483

_MEMORY: dict[str, list[dict[str, Any]]] = {}
_MEMORY_LOCKS: dict[str, threading.Lock] = {}
_MEMORY_META = threading.Lock()


def _memory_bucket(dsn: str) -> tuple[list[dict[str, Any]], threading.Lock]:
    with _MEMORY_META:
        if dsn not in _MEMORY:
            _MEMORY[dsn] = []
            _MEMORY_LOCKS[dsn] = threading.Lock()
        return _MEMORY[dsn], _MEMORY_LOCKS[dsn]


class PostgresAuditLog:
    """Fleet-shared append-only audit trail with one global hash chain (#483)."""

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
                "enterprise.audit_backend=postgres requires psycopg — "
                "pip install 'psycopg[binary]>=3' (or daari[postgres])"
            ) from exc
        return psycopg.connect(self.dsn)

    def record(
        self,
        *,
        actor: str,
        role: str,
        action: str,
        detail: dict[str, Any] | None = None,
    ) -> None:
        if not self.enabled:
            return
        try:
            detail_s = json.dumps(detail or {})
            ts = datetime.now(timezone.utc).isoformat()
            if self._memory:
                rows, lock = _memory_bucket(self.dsn)
                with lock:
                    tip = next(
                        (r for r in reversed(rows) if r.get("row_hash")),
                        None,
                    )
                    prev_hash = tip["row_hash"] if tip else GENESIS_HASH
                    next_seq = (rows[-1]["seq"] + 1) if rows else 1
                    row_hash = compute_row_hash(
                        int(next_seq), ts, actor, role, action, detail_s, prev_hash
                    )
                    rows.append(
                        {
                            "seq": int(next_seq),
                            "ts": ts,
                            "actor": actor,
                            "role": role,
                            "action": action,
                            "detail": detail_s,
                            "prev_hash": prev_hash,
                            "row_hash": row_hash,
                        }
                    )
                return
            with self._lock:
                with self._connect() as conn:
                    with conn.cursor() as cur:
                        cur.execute("SELECT pg_advisory_xact_lock(%s)", (_AUDIT_LOCK_KEY,))
                        cur.execute(
                            "SELECT row_hash FROM daari_audit WHERE row_hash IS NOT NULL "
                            "ORDER BY seq DESC LIMIT 1"
                        )
                        tip = cur.fetchone()
                        prev_hash = tip[0] if tip and tip[0] else GENESIS_HASH
                        cur.execute("SELECT COALESCE(MAX(seq), 0) + 1 FROM daari_audit")
                        next_seq = int(cur.fetchone()[0])
                        row_hash = compute_row_hash(
                            next_seq, ts, actor, role, action, detail_s, prev_hash
                        )
                        cur.execute(
                            "INSERT INTO daari_audit"
                            " (seq, ts, actor, role, action, detail, prev_hash, row_hash)"
                            " VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                            (
                                next_seq,
                                ts,
                                actor,
                                role,
                                action,
                                detail_s,
                                prev_hash,
                                row_hash,
                            ),
                        )
                    conn.commit()
        except Exception:
            pass

    def list(
        self,
        limit: int = 100,
        *,
        actor: str | None = None,
        action: str | None = None,
        since: str | None = None,
    ) -> list[dict[str, Any]]:
        return list(
            self.iter_rows(limit=limit, actor=actor, action=action, since=since, batch_size=limit)
        )

    def iter_rows(
        self,
        *,
        limit: int | None = None,
        actor: str | None = None,
        action: str | None = None,
        since: str | None = None,
        batch_size: int = 500,
    ) -> Iterator[dict[str, Any]]:
        if not self.enabled:
            return
        remaining = None if limit is None else max(0, int(limit))
        if remaining == 0:
            return
        if self._memory:
            rows, lock = _memory_bucket(self.dsn)
            with lock:
                snapshot = list(rows)
            action_prefix = (action or "").strip()
            actor_filter = (actor or "").strip() or None
            yielded = 0
            for row in reversed(snapshot):
                if actor_filter and row["actor"] != actor_filter:
                    continue
                if action_prefix and not str(row["action"]).startswith(action_prefix):
                    continue
                if since and row["ts"] < since:
                    continue
                yield _row_dict(
                    row["seq"],
                    row["ts"],
                    row["actor"],
                    row["role"],
                    row["action"],
                    row["detail"],
                    row.get("prev_hash"),
                    row.get("row_hash"),
                )
                yielded += 1
                if remaining is not None and yielded >= remaining:
                    return
            return
        cursor_seq: int | None = None
        batch = max(1, int(batch_size))
        action_prefix = (action or "").strip()
        actor_filter = (actor or "").strip() or None
        while True:
            take = batch if remaining is None else min(batch, remaining)
            if take <= 0:
                return
            clauses = ["1=1"]
            params: list[Any] = []
            if actor_filter:
                clauses.append("actor = %s")
                params.append(actor_filter)
            if action_prefix:
                clauses.append("action LIKE %s")
                params.append(f"{action_prefix}%")
            if since:
                clauses.append("ts >= %s")
                params.append(since)
            if cursor_seq is not None:
                clauses.append("seq < %s")
                params.append(cursor_seq)
            params.append(take)
            sql = (
                "SELECT seq, ts, actor, role, action, detail, prev_hash, row_hash"
                " FROM daari_audit WHERE "
                + " AND ".join(clauses)
                + " ORDER BY seq DESC LIMIT %s"
            )
            try:
                with self._lock:
                    with self._connect() as conn:
                        with conn.cursor() as cur:
                            cur.execute(sql, params)
                            fetched = cur.fetchall()
            except Exception:
                return
            if not fetched:
                return
            for seq, ts, row_actor, role, row_action, detail, prev_hash, row_hash in fetched:
                yield _row_dict(
                    seq, ts, row_actor, role, row_action, detail, prev_hash, row_hash
                )
                cursor_seq = int(seq)
                if remaining is not None:
                    remaining -= 1
                    if remaining <= 0:
                        return

    def verify(self) -> VerifyResult:
        if not self.enabled:
            return VerifyResult(ok=False, total=0, legacy=0, chained=0, reason="disabled")
        try:
            if self._memory:
                rows_data, lock = _memory_bucket(self.dsn)
                with lock:
                    rows = [
                        (
                            r["seq"],
                            r["ts"],
                            r["actor"],
                            r["role"],
                            r["action"],
                            r["detail"],
                            r.get("prev_hash"),
                            r.get("row_hash"),
                        )
                        for r in rows_data
                    ]
            else:
                with self._lock:
                    with self._connect() as conn:
                        with conn.cursor() as cur:
                            cur.execute(
                                "SELECT seq, ts, actor, role, action, detail,"
                                " prev_hash, row_hash FROM daari_audit ORDER BY seq ASC"
                            )
                            rows = cur.fetchall()
        except Exception:
            return VerifyResult(ok=False, total=0, legacy=0, chained=0, reason="read_failed")
        total = len(rows)
        legacy = 0
        chained = 0
        expected_prev = GENESIS_HASH
        last_seq: int | None = None
        for seq, ts, actor, role, action, detail, prev_hash, row_hash in rows:
            seq_i = int(seq)
            if last_seq is not None and seq_i != last_seq + 1:
                return VerifyResult(
                    ok=False,
                    total=total,
                    legacy=legacy,
                    chained=chained,
                    broken_seq=seq_i,
                    reason="seq_gap",
                )
            last_seq = seq_i
            if not row_hash:
                legacy += 1
                continue
            if prev_hash != expected_prev:
                return VerifyResult(
                    ok=False,
                    total=total,
                    legacy=legacy,
                    chained=chained,
                    broken_seq=seq_i,
                    reason="hash_mismatch",
                )
            recomputed = compute_row_hash(
                seq_i, ts, actor, role, action, detail or "", prev_hash or GENESIS_HASH
            )
            if recomputed != row_hash:
                return VerifyResult(
                    ok=False,
                    total=total,
                    legacy=legacy,
                    chained=chained,
                    broken_seq=seq_i,
                    reason="hash_mismatch",
                )
            chained += 1
            expected_prev = row_hash
        return VerifyResult(ok=True, total=total, legacy=legacy, chained=chained)

    def prune_before(self, cutoff: str, *, dry_run: bool = False) -> int:
        if not self.enabled:
            return 0
        try:
            if self._memory:
                rows, lock = _memory_bucket(self.dsn)
                with lock:
                    doomed = [r for r in rows if r["ts"] < cutoff]
                    if dry_run or not doomed:
                        return len(doomed)
                    keep = [r for r in rows if r["ts"] >= cutoff]
                    prev = GENESIS_HASH
                    for row in keep:
                        if not row.get("row_hash"):
                            continue
                        row_hash = compute_row_hash(
                            int(row["seq"]),
                            row["ts"],
                            row["actor"],
                            row["role"],
                            row["action"],
                            row["detail"] or "",
                            prev,
                        )
                        row["prev_hash"] = prev
                        row["row_hash"] = row_hash
                        prev = row_hash
                    rows[:] = keep
                    return len(doomed)
            with self._lock:
                with self._connect() as conn:
                    with conn.cursor() as cur:
                        cur.execute(
                            "SELECT COUNT(*) FROM daari_audit WHERE ts < %s", (cutoff,)
                        )
                        count = int(cur.fetchone()[0])
                        if not dry_run and count:
                            cur.execute("DELETE FROM daari_audit WHERE ts < %s", (cutoff,))
                            cur.execute(
                                "SELECT seq, ts, actor, role, action, detail FROM daari_audit"
                                " WHERE row_hash IS NOT NULL ORDER BY seq ASC"
                            )
                            chained = cur.fetchall()
                            prev = GENESIS_HASH
                            for seq, ts, actor, role, action, detail in chained:
                                row_hash = compute_row_hash(
                                    int(seq),
                                    ts,
                                    actor,
                                    role,
                                    action,
                                    detail or "",
                                    prev,
                                )
                                cur.execute(
                                    "UPDATE daari_audit SET prev_hash = %s, row_hash = %s"
                                    " WHERE seq = %s",
                                    (prev, row_hash, int(seq)),
                                )
                                prev = row_hash
                    conn.commit()
                    return count
        except Exception:
            return 0


def audit_log_from_settings(settings: Any):
    """Construct SQLite or Postgres AuditLog from settings (#483)."""
    from daari.enterprise.audit import AuditLog

    enterprise = getattr(settings, "enterprise", None)
    backend = getattr(enterprise, "audit_backend", "sqlite") or "sqlite"
    pg_url = (
        getattr(getattr(settings, "observability", None), "postgres_url", "") or ""
    ).strip()
    if backend == "postgres" and pg_url:
        return PostgresAuditLog(pg_url)
    path = getattr(enterprise, "audit_path", "~/.daari/audit/audit.sqlite3")
    return AuditLog(path)
