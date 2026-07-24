"""Append-only audit log for admin actions (issue #119)."""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

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

    def list(self, limit: int = 100) -> list[dict[str, Any]]:
        if not self.enabled:
            return []
        try:
            with self._lock, self._connect() as conn:
                rows = conn.execute(
                    "SELECT ts, actor, role, action, detail FROM audit"
                    " ORDER BY seq DESC LIMIT ?",
                    (max(1, limit),),
                ).fetchall()
            return [
                {
                    "ts": ts,
                    "actor": actor,
                    "role": role,
                    "action": action,
                    "detail": json.loads(detail),
                }
                for ts, actor, role, action, detail in rows
            ]
        except Exception:
            return []
