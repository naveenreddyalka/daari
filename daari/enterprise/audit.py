"""Append-only audit log for admin actions (issue #119, #345)."""

from __future__ import annotations

import json
import re
import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator

_SCHEMA = """
CREATE TABLE IF NOT EXISTS audit (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    actor TEXT NOT NULL,
    role TEXT NOT NULL,
    action TEXT NOT NULL,
    detail TEXT NOT NULL
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


def _row_dict(seq: int, ts: str, actor: str, role: str, action: str, detail: str) -> dict[str, Any]:
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
            except Exception:
                self.enabled = False

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path, timeout=5.0)

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
                conn.execute(
                    "INSERT INTO audit (ts, actor, role, action, detail) VALUES (?, ?, ?, ?, ?)",
                    (
                        datetime.now(timezone.utc).isoformat(),
                        actor,
                        role,
                        action,
                        json.dumps(detail or {}),
                    ),
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
                "SELECT seq, ts, actor, role, action, detail FROM audit WHERE "
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
            for seq, ts, row_actor, role, row_action, detail in rows:
                yield _row_dict(seq, ts, row_actor, role, row_action, detail)
                cursor_seq = int(seq)
                if remaining is not None:
                    remaining -= 1
                    if remaining <= 0:
                        return

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
                return int(count)
        except Exception:
            return 0
