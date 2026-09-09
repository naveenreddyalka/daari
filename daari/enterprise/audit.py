"""Append-only audit log for admin actions (issue #119, #345, #378).

Rows written after the hash-chain upgrade carry `prev_hash` / `row_hash`
(SHA-256). Pre-upgrade rows verify as `legacy`. Retention prune re-anchors
the chain head so truncated logs still verify.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator

# Documented genesis for the first chained row (and after prune re-anchor).
GENESIS_HASH = "0" * 64

_SCHEMA = """
CREATE TABLE IF NOT EXISTS audit (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    actor TEXT NOT NULL,
    role TEXT NOT NULL,
    action TEXT NOT NULL,
    detail TEXT NOT NULL,
    prev_hash TEXT,
    row_hash TEXT
);
"""

_RELATIVE_SINCE = re.compile(r"^(\d+)([dhms])$", re.IGNORECASE)


def parse_since(raw: str, *, now: datetime | None = None) -> str:
    """Return an ISO-8601 UTC cutoff. Accepts ISO timestamps or relative `7d` / `12h`."""
    text = (raw or "").strip()
    if not text:
        raise ValueError("since value is empty")
    moment = now or datetime.now(timezone.utc)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    match = _RELATIVE_SINCE.match(text)
    if match:
        amount = int(match.group(1))
        unit = match.group(2).lower()
        delta = {
            "d": timedelta(days=amount),
            "h": timedelta(hours=amount),
            "m": timedelta(minutes=amount),
            "s": timedelta(seconds=amount),
        }[unit]
        return (moment - delta).isoformat()
    normalized = text.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ValueError(f"invalid since value: {raw!r}") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat()


def compute_row_hash(
    seq: int,
    ts: str,
    actor: str,
    role: str,
    action: str,
    detail: str,
    prev_hash: str,
) -> str:
    """SHA-256 over a canonical JSON serialization of the chained fields."""
    payload = json.dumps(
        {
            "action": action,
            "actor": actor,
            "detail": detail,
            "prev_hash": prev_hash,
            "role": role,
            "seq": int(seq),
            "ts": ts,
        },
        separators=(",", ":"),
        sort_keys=True,
        ensure_ascii=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _row_dict(
    seq: int,
    ts: str,
    actor: str,
    role: str,
    action: str,
    detail: str,
    prev_hash: str | None = None,
    row_hash: str | None = None,
) -> dict[str, Any]:
    try:
        payload = json.loads(detail)
    except json.JSONDecodeError:
        payload = {"raw": detail}
    return {
        "seq": int(seq),
        "ts": ts,
        "actor": actor,
        "role": role,
        "action": action,
        "detail": payload,
        "prev_hash": prev_hash,
        "row_hash": row_hash,
    }


@dataclass(frozen=True)
class VerifyResult:
    ok: bool
    total: int
    legacy: int
    chained: int
    broken_seq: int | None = None
    reason: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "total": self.total,
            "legacy": self.legacy,
            "chained": self.chained,
            "broken_seq": self.broken_seq,
            "reason": self.reason,
        }


class AuditLog:
    def __init__(self, path: str | Path, enabled: bool = True) -> None:
        self.path = Path(path).expanduser()
        self.enabled = enabled
        self._lock = threading.Lock()
        if self.enabled:
            try:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                with self._connect() as conn:
                    conn.execute(_SCHEMA)
                    self._migrate(conn)
            except Exception:
                self.enabled = False

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path, timeout=5.0)

    @staticmethod
    def _migrate(conn: sqlite3.Connection) -> None:
        cols = {row[1] for row in conn.execute("PRAGMA table_info(audit)")}
        if "prev_hash" not in cols:
            conn.execute("ALTER TABLE audit ADD COLUMN prev_hash TEXT")
        if "row_hash" not in cols:
            conn.execute("ALTER TABLE audit ADD COLUMN row_hash TEXT")

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
            with self._lock, self._connect() as conn:
                tip = conn.execute(
                    "SELECT row_hash FROM audit WHERE row_hash IS NOT NULL "
                    "ORDER BY seq DESC LIMIT 1"
                ).fetchone()
                prev_hash = tip[0] if tip and tip[0] else GENESIS_HASH
                next_seq = conn.execute(
                    "SELECT COALESCE(MAX(seq), 0) + 1 FROM audit"
                ).fetchone()[0]
                ts = datetime.now(timezone.utc).isoformat()
                detail_s = json.dumps(detail or {})
                row_hash = compute_row_hash(
                    int(next_seq), ts, actor, role, action, detail_s, prev_hash
                )
                conn.execute(
                    "INSERT INTO audit (seq, ts, actor, role, action, detail, prev_hash, row_hash)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (int(next_seq), ts, actor, role, action, detail_s, prev_hash, row_hash),
                )
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
        """Newest-first filtered scan in seq batches (no full-table load)."""
        if not self.enabled:
            return
        remaining = None if limit is None else max(0, int(limit))
        if remaining == 0:
            return
        cursor_seq: int | None = None
        batch = max(1, int(batch_size))
        action_prefix = (action or "").strip()
        actor_filter = (actor or "").strip() or None
        since_cutoff = since
        while True:
            take = batch if remaining is None else min(batch, remaining)
            if take <= 0:
                return
            clauses = ["1=1"]
            params: list[Any] = []
            if actor_filter:
                clauses.append("actor = ?")
                params.append(actor_filter)
            if action_prefix:
                clauses.append("action LIKE ?")
                params.append(f"{action_prefix}%")
            if since_cutoff:
                clauses.append("ts >= ?")
                params.append(since_cutoff)
            if cursor_seq is not None:
                clauses.append("seq < ?")
                params.append(cursor_seq)
            params.append(take)
            sql = (
                "SELECT seq, ts, actor, role, action, detail, prev_hash, row_hash FROM audit WHERE "
                + " AND ".join(clauses)
                + " ORDER BY seq DESC LIMIT ?"
            )
            try:
                with self._lock, self._connect() as conn:
                    rows = conn.execute(sql, params).fetchall()
            except Exception:
                return
            if not rows:
                return
            for seq, ts, row_actor, role, row_action, detail, prev_hash, row_hash in rows:
                yield _row_dict(
                    seq, ts, row_actor, role, row_action, detail, prev_hash, row_hash
                )
                cursor_seq = int(seq)
                if remaining is not None:
                    remaining -= 1
                    if remaining <= 0:
                        return

    def verify(self) -> VerifyResult:
        """Walk oldest-first; legacy (NULL row_hash) counted; chain from first hashed row."""
        if not self.enabled:
            return VerifyResult(ok=False, total=0, legacy=0, chained=0, reason="disabled")
        try:
            with self._lock, self._connect() as conn:
                rows = conn.execute(
                    "SELECT seq, ts, actor, role, action, detail, prev_hash, row_hash"
                    " FROM audit ORDER BY seq ASC"
                ).fetchall()
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
            with self._lock, self._connect() as conn:
                count = conn.execute(
                    "SELECT COUNT(*) FROM audit WHERE ts < ?", (cutoff,)
                ).fetchone()[0]
                if not dry_run and count:
                    conn.execute("DELETE FROM audit WHERE ts < ?", (cutoff,))
                    self._reanchor_chain(conn)
                return int(count)
        except Exception:
            return 0

    @staticmethod
    def _reanchor_chain(conn: sqlite3.Connection) -> None:
        """Rebuild prev_hash/row_hash from GENESIS after pruning (#378)."""
        rows = conn.execute(
            "SELECT seq, ts, actor, role, action, detail FROM audit"
            " WHERE row_hash IS NOT NULL ORDER BY seq ASC"
        ).fetchall()
        prev = GENESIS_HASH
        for seq, ts, actor, role, action, detail in rows:
            row_hash = compute_row_hash(
                int(seq), ts, actor, role, action, detail or "", prev
            )
            conn.execute(
                "UPDATE audit SET prev_hash = ?, row_hash = ? WHERE seq = ?",
                (prev, row_hash, int(seq)),
            )
            prev = row_hash
