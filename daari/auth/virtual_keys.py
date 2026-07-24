"""Virtual API keys with per-key budgets, RPM, and tier caps (issue #111).

Keys are stored hashed (sha256) in SQLite. The plaintext is shown once at
create time. The master `server.api_key` remains valid alongside virtual keys.
"""

from __future__ import annotations

import hashlib
import secrets
import sqlite3
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_SCHEMA = """
CREATE TABLE IF NOT EXISTS virtual_keys (
    key_hash TEXT PRIMARY KEY,
    key_id TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    prefix TEXT NOT NULL,
    created_at TEXT NOT NULL,
    revoked_at TEXT,
    daily_budget_usd REAL NOT NULL DEFAULT 0,
    monthly_budget_usd REAL NOT NULL DEFAULT 0,
    rpm INTEGER NOT NULL DEFAULT 0,
    tier_cap TEXT,
    client_id TEXT
);
CREATE TABLE IF NOT EXISTS key_hits (
    key_id TEXT NOT NULL,
    ts REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_key_hits_key_ts ON key_hits(key_id, ts);
"""


@dataclass(frozen=True)
class VirtualKey:
    key_id: str
    name: str
    prefix: str
    daily_budget_usd: float = 0.0
    monthly_budget_usd: float = 0.0
    rpm: int = 0
    tier_cap: str | None = None
    client_id: str | None = None
    revoked: bool = False


@dataclass(frozen=True)
class CreatedKey:
    key: VirtualKey
    plaintext: str


class VirtualKeyStore:
    def __init__(self, path: str | Path, enabled: bool = True) -> None:
        self.path = Path(path).expanduser()
        self.enabled = enabled
        self._lock = threading.Lock()
        if self.enabled:
            try:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                with self._connect() as conn:
                    conn.executescript(_SCHEMA)
            except Exception:
                self.enabled = False

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path, timeout=5.0)

    @staticmethod
    def _hash(plaintext: str) -> str:
        return hashlib.sha256(plaintext.encode("utf-8")).hexdigest()

    def create(
        self,
        name: str,
        *,
        daily_budget_usd: float = 0.0,
        monthly_budget_usd: float = 0.0,
        rpm: int = 0,
        tier_cap: str | None = None,
        client_id: str | None = None,
    ) -> CreatedKey:
        if not self.enabled:
            raise RuntimeError("virtual key store is disabled")
        plaintext = f"dk_{secrets.token_urlsafe(32)}"
        key_id = secrets.token_hex(8)
        prefix = plaintext[:10]
        created = datetime.now(timezone.utc).isoformat()
        with self._lock, self._connect() as conn:
            conn.execute(
                "INSERT INTO virtual_keys (key_hash, key_id, name, prefix, created_at,"
                " daily_budget_usd, monthly_budget_usd, rpm, tier_cap, client_id)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    self._hash(plaintext),
                    key_id,
                    name,
                    prefix,
                    created,
                    float(daily_budget_usd),
                    float(monthly_budget_usd),
                    int(rpm),
                    tier_cap,
                    client_id,
                ),
            )
        return CreatedKey(
            key=VirtualKey(
                key_id=key_id,
                name=name,
                prefix=prefix,
                daily_budget_usd=daily_budget_usd,
                monthly_budget_usd=monthly_budget_usd,
                rpm=rpm,
                tier_cap=tier_cap,
                client_id=client_id,
            ),
            plaintext=plaintext,
        )

    def revoke(self, key_id: str) -> bool:
        if not self.enabled:
            return False
        with self._lock, self._connect() as conn:
            cur = conn.execute(
                "UPDATE virtual_keys SET revoked_at = ? WHERE key_id = ? AND revoked_at IS NULL",
                (datetime.now(timezone.utc).isoformat(), key_id),
            )
            return cur.rowcount > 0

    def list(self) -> list[VirtualKey]:
        if not self.enabled:
            return []
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                "SELECT key_id, name, prefix, daily_budget_usd, monthly_budget_usd,"
                " rpm, tier_cap, client_id, revoked_at FROM virtual_keys"
                " ORDER BY created_at DESC"
            ).fetchall()
        return [
            VirtualKey(
                key_id=r[0],
                name=r[1],
                prefix=r[2],
                daily_budget_usd=r[3],
                monthly_budget_usd=r[4],
                rpm=r[5],
                tier_cap=r[6],
                client_id=r[7],
                revoked=r[8] is not None,
            )
            for r in rows
        ]

    def resolve(self, plaintext: str) -> VirtualKey | None:
        if not self.enabled or not plaintext:
            return None
        digest = self._hash(plaintext)
        with self._lock, self._connect() as conn:
            row = conn.execute(
                "SELECT key_id, name, prefix, daily_budget_usd, monthly_budget_usd,"
                " rpm, tier_cap, client_id, revoked_at FROM virtual_keys"
                " WHERE key_hash = ?",
                (digest,),
            ).fetchone()
        if row is None or row[8] is not None:
            return None
        return VirtualKey(
            key_id=row[0],
            name=row[1],
            prefix=row[2],
            daily_budget_usd=row[3],
            monthly_budget_usd=row[4],
            rpm=row[5],
            tier_cap=row[6],
            client_id=row[7],
            revoked=False,
        )

    def check_rpm(self, key: VirtualKey) -> bool:
        """Return True if the request is within the RPM limit (and record the hit)."""
        if not self.enabled or key.rpm <= 0:
            return True
        now = time.time()
        window_start = now - 60.0
        with self._lock, self._connect() as conn:
            conn.execute("DELETE FROM key_hits WHERE ts < ?", (window_start,))
            count = conn.execute(
                "SELECT COUNT(*) FROM key_hits WHERE key_id = ? AND ts >= ?",
                (key.key_id, window_start),
            ).fetchone()[0]
            if count >= key.rpm:
                return False
            conn.execute(
                "INSERT INTO key_hits (key_id, ts) VALUES (?, ?)", (key.key_id, now)
            )
            return True

    def to_dict(self, key: VirtualKey) -> dict[str, Any]:
        return {
            "key_id": key.key_id,
            "name": key.name,
            "prefix": key.prefix,
            "daily_budget_usd": key.daily_budget_usd,
            "monthly_budget_usd": key.monthly_budget_usd,
            "rpm": key.rpm,
            "tier_cap": key.tier_cap,
            "client_id": key.client_id,
            "revoked": key.revoked,
        }
