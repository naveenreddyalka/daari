"""Virtual API keys with per-key budgets, RPM, and tier caps (issue #111).

Keys are stored hashed (sha256) in SQLite. The plaintext is shown once at
create time. The master `server.api_key` remains valid alongside virtual keys.
"""

from __future__ import annotations

import hashlib
import json
import re
import secrets
import sqlite3
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

_RELATIVE_EXPIRY = re.compile(r"^(\d+)([mhd])$")
_NEVER_EXPIRES = {"", "never", "none", "0"}


def expiry_from(raw: str | None, *, now: datetime | None = None) -> str | None:
    """Turn `30d` / `12h` / `45m` / ISO-8601 into a UTC ISO timestamp (#331).

    None, empty, or `never` mean the key does not expire. Relative durations
    must be positive; ISO values without a zone are taken as UTC.
    """
    value = (raw or "").strip()
    if value.lower() in _NEVER_EXPIRES:
        return None
    current = now if now is not None else datetime.now(timezone.utc)
    match = _RELATIVE_EXPIRY.match(value.lower())
    if match:
        amount, unit = int(match.group(1)), match.group(2)
        if amount <= 0:
            raise ValueError(f"expiry must be positive: {raw!r}")
        delta = {
            "m": timedelta(minutes=amount),
            "h": timedelta(hours=amount),
            "d": timedelta(days=amount),
        }
        return (current + delta[unit]).isoformat()
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ValueError(
            f"unsupported expiry {raw!r} — use <n>m, <n>h, <n>d, or an ISO-8601 timestamp"
        ) from None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat()


def _is_past(iso: str | None, now: datetime | None = None) -> bool:
    if not iso:
        return False
    try:
        when = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except ValueError:
        return False
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    current = now if now is not None else datetime.now(timezone.utc)
    return when <= current


_SCHEMA = """
CREATE TABLE IF NOT EXISTS teams (
    team_id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    budget_windows_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS virtual_keys (
    key_hash TEXT PRIMARY KEY,
    key_id TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    prefix TEXT NOT NULL,
    created_at TEXT NOT NULL,
    revoked_at TEXT,
    expires_at TEXT,
    daily_budget_usd REAL NOT NULL DEFAULT 0,
    monthly_budget_usd REAL NOT NULL DEFAULT 0,
    rpm INTEGER NOT NULL DEFAULT 0,
    tpm INTEGER NOT NULL DEFAULT 0,
    tier_cap TEXT,
    client_id TEXT,
    team_id TEXT,
    budget_windows_json TEXT NOT NULL DEFAULT '[]',
    metadata_json TEXT NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS key_hits (
    key_id TEXT NOT NULL,
    ts REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_key_hits_key_ts ON key_hits(key_id, ts);
"""


@dataclass(frozen=True)
class BudgetWindow:
    duration: str
    max_usd: float

    def as_dict(self) -> dict[str, Any]:
        return {"duration": self.duration, "max_usd": float(self.max_usd)}


@dataclass(frozen=True)
class Team:
    team_id: str
    name: str
    budget_windows: tuple[BudgetWindow, ...] = ()


@dataclass(frozen=True)
class VirtualKey:
    key_id: str
    name: str
    prefix: str
    daily_budget_usd: float = 0.0
    monthly_budget_usd: float = 0.0
    rpm: int = 0
    tpm: int = 0
    tier_cap: str | None = None
    client_id: str | None = None
    revoked: bool = False
    team_id: str | None = None
    team_name: str | None = None
    budget_windows: tuple[BudgetWindow, ...] = field(default_factory=tuple)
    metadata: dict[str, Any] = field(default_factory=dict)
    # ISO-8601 UTC; None = never expires (#331).
    expires_at: str | None = None

    def is_expired(self, now: datetime | None = None) -> bool:
        return _is_past(self.expires_at, now)

    def status(self, now: datetime | None = None) -> str:
        """`revoked` beats `expired` beats `active` — revocation is explicit."""
        if self.revoked:
            return "revoked"
        if self.is_expired(now):
            return "expired"
        return "active"


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
                    self._migrate(conn)
            except Exception:
                self.enabled = False

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path, timeout=5.0)

    @staticmethod
    def _windows_json(windows: list[BudgetWindow] | tuple[BudgetWindow, ...] | None) -> str:
        return json.dumps([w.as_dict() for w in (windows or ())])

    @staticmethod
    def _parse_windows(raw: str | None) -> tuple[BudgetWindow, ...]:
        if not raw:
            return ()
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return ()
        out: list[BudgetWindow] = []
        for item in payload or []:
            if not isinstance(item, dict):
                continue
            duration = str(item.get("duration") or "").strip()
            try:
                max_usd = float(item.get("max_usd") or 0)
            except (TypeError, ValueError):
                continue
            if duration and max_usd > 0:
                out.append(BudgetWindow(duration, max_usd))
        return tuple(out)

    def _migrate(self, conn: sqlite3.Connection) -> None:
        cols = {row[1] for row in conn.execute("PRAGMA table_info(virtual_keys)")}
        if "tpm" not in cols:
            conn.execute("ALTER TABLE virtual_keys ADD COLUMN tpm INTEGER NOT NULL DEFAULT 0")
        if "team_id" not in cols:
            conn.execute("ALTER TABLE virtual_keys ADD COLUMN team_id TEXT")
        if "budget_windows_json" not in cols:
            conn.execute(
                "ALTER TABLE virtual_keys ADD COLUMN budget_windows_json TEXT NOT NULL DEFAULT '[]'"
            )
        if "metadata_json" not in cols:
            conn.execute(
                "ALTER TABLE virtual_keys ADD COLUMN metadata_json TEXT NOT NULL DEFAULT '{}'"
            )
        if "expires_at" not in cols:
            # NULL for every pre-#331 key: existing keys never expire.
            conn.execute("ALTER TABLE virtual_keys ADD COLUMN expires_at TEXT")
        rows = conn.execute(
            "SELECT key_id, daily_budget_usd, monthly_budget_usd, budget_windows_json"
            " FROM virtual_keys"
        ).fetchall()
        for key_id, daily, monthly, raw in rows:
            if self._parse_windows(raw):
                continue
            windows = []
            if float(daily or 0) > 0:
                windows.append(BudgetWindow("day", float(daily)))
            if float(monthly or 0) > 0:
                windows.append(BudgetWindow("month", float(monthly)))
            if windows:
                conn.execute(
                    "UPDATE virtual_keys SET budget_windows_json = ? WHERE key_id = ?",
                    (self._windows_json(windows), key_id),
                )

    @staticmethod
    def _hash(plaintext: str) -> str:
        return hashlib.sha256(plaintext.encode("utf-8")).hexdigest()

    def create_team(
        self,
        name: str,
        *,
        budget_windows: list[BudgetWindow] | None = None,
        daily_budget_usd: float = 0.0,
        monthly_budget_usd: float = 0.0,
    ) -> Team:
        if not self.enabled:
            raise RuntimeError("virtual key store is disabled")
        windows = tuple(budget_windows or ())
        if not windows:
            from daari.auth.budgets import windows_from_flat

            windows = windows_from_flat(daily_usd=daily_budget_usd, monthly_usd=monthly_budget_usd)
        team_id = secrets.token_hex(8)
        created = datetime.now(timezone.utc).isoformat()
        with self._lock, self._connect() as conn:
            existing = conn.execute(
                "SELECT team_id, budget_windows_json FROM teams WHERE name = ?", (name,)
            ).fetchone()
            if existing:
                return Team(
                    team_id=existing[0],
                    name=name,
                    budget_windows=self._parse_windows(existing[1]),
                )
            conn.execute(
                "INSERT INTO teams (team_id, name, budget_windows_json, created_at)"
                " VALUES (?, ?, ?, ?)",
                (team_id, name, self._windows_json(windows), created),
            )
        return Team(team_id=team_id, name=name, budget_windows=windows)

    def get_team(self, team_id: str | None = None, *, name: str | None = None) -> Team | None:
        if not self.enabled or (not team_id and not name):
            return None
        with self._lock, self._connect() as conn:
            if team_id:
                row = conn.execute(
                    "SELECT team_id, name, budget_windows_json FROM teams WHERE team_id = ?",
                    (team_id,),
                ).fetchone()
            else:
                row = conn.execute(
                    "SELECT team_id, name, budget_windows_json FROM teams WHERE name = ?",
                    (name,),
                ).fetchone()
        if row is None:
            return None
        return Team(team_id=row[0], name=row[1], budget_windows=self._parse_windows(row[2]))

    def team_client_ids(self, team_id: str) -> list[str]:
        if not self.enabled:
            return []
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                "SELECT key_id, client_id FROM virtual_keys"
                " WHERE team_id = ? AND revoked_at IS NULL",
                (team_id,),
            ).fetchall()
        return [row[1] or row[0] for row in rows]

    def create(
        self,
        name: str,
        *,
        daily_budget_usd: float = 0.0,
        monthly_budget_usd: float = 0.0,
        rpm: int = 0,
        tpm: int = 0,
        tier_cap: str | None = None,
        client_id: str | None = None,
        team: str | None = None,
        budget_windows: list[BudgetWindow] | None = None,
        metadata: dict[str, Any] | None = None,
        expires_at: str | None = None,
    ) -> CreatedKey:
        if not self.enabled:
            raise RuntimeError("virtual key store is disabled")
        from daari.auth.budgets import windows_from_flat

        # Normalise whatever the caller passed (relative or ISO) once, here.
        expires_at = expiry_from(expires_at)
        plaintext = f"dk_{secrets.token_urlsafe(32)}"
        key_id = secrets.token_hex(8)
        prefix = plaintext[:10]
        created = datetime.now(timezone.utc).isoformat()
        team_row = self.create_team(team) if team else None
        windows = tuple(budget_windows or ())
        seen = {item.duration for item in windows}
        for item in windows_from_flat(daily_usd=daily_budget_usd, monthly_usd=monthly_budget_usd):
            if item.duration not in seen:
                windows = windows + (item,)
                seen.add(item.duration)
        with self._lock, self._connect() as conn:
            conn.execute(
                "INSERT INTO virtual_keys (key_hash, key_id, name, prefix, created_at,"
                " daily_budget_usd, monthly_budget_usd, rpm, tpm, tier_cap, client_id,"
                " team_id, budget_windows_json, metadata_json, expires_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    self._hash(plaintext),
                    key_id,
                    name,
                    prefix,
                    created,
                    float(daily_budget_usd),
                    float(monthly_budget_usd),
                    int(rpm),
                    int(tpm),
                    tier_cap,
                    client_id,
                    team_row.team_id if team_row else None,
                    self._windows_json(windows),
                    json.dumps(metadata or {}),
                    expires_at,
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
                tpm=tpm,
                tier_cap=tier_cap,
                client_id=client_id,
                team_id=team_row.team_id if team_row else None,
                team_name=team_row.name if team_row else None,
                budget_windows=windows,
                metadata=dict(metadata or {}),
                expires_at=expires_at,
            ),
            plaintext=plaintext,
        )

    def update_limits(
        self,
        key_id: str,
        *,
        daily_budget_usd: float = 0.0,
        monthly_budget_usd: float = 0.0,
        rpm: int = 0,
        tpm: int = 0,
        tier_cap: str | None = None,
        team: str | None = None,
        budget_windows: list[BudgetWindow] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        if not self.enabled:
            return False
        from daari.auth.budgets import windows_from_flat

        team_row = self.create_team(team) if team else None
        windows = tuple(budget_windows or ())
        seen = {item.duration for item in windows}
        for item in windows_from_flat(daily_usd=daily_budget_usd, monthly_usd=monthly_budget_usd):
            if item.duration not in seen:
                windows = windows + (item,)
                seen.add(item.duration)
        with self._lock, self._connect() as conn:
            cur = conn.execute(
                "UPDATE virtual_keys SET daily_budget_usd = ?, monthly_budget_usd = ?,"
                " rpm = ?, tpm = ?, tier_cap = ?, team_id = ?, budget_windows_json = ?,"
                " metadata_json = ? WHERE key_id = ? AND revoked_at IS NULL",
                (
                    float(daily_budget_usd),
                    float(monthly_budget_usd),
                    int(rpm),
                    int(tpm),
                    tier_cap,
                    team_row.team_id if team_row else None,
                    self._windows_json(windows),
                    json.dumps(metadata or {}),
                    key_id,
                ),
            )
            return cur.rowcount > 0

    def revoke(self, key_id: str) -> bool:
        if not self.enabled:
            return False
        with self._lock, self._connect() as conn:
            cur = conn.execute(
                "UPDATE virtual_keys SET revoked_at = ? WHERE key_id = ? AND revoked_at IS NULL",
                (datetime.now(timezone.utc).isoformat(), key_id),
            )
            return cur.rowcount > 0

    def _key_from_row(
        self,
        row: tuple[Any, ...],
        *,
        team_name: str | None = None,
        metadata: dict[str, Any] | None = None,
        expires_at: str | None = None,
    ) -> VirtualKey:
        windows = self._parse_windows(row[11] if len(row) > 11 else None)
        if not windows:
            from daari.auth.budgets import windows_from_flat

            windows = windows_from_flat(
                daily_usd=float(row[3] or 0), monthly_usd=float(row[4] or 0)
            )
        parsed = metadata or {}
        return VirtualKey(
            key_id=row[0],
            name=row[1],
            prefix=row[2],
            daily_budget_usd=row[3],
            monthly_budget_usd=row[4],
            rpm=row[5],
            tpm=row[6],
            tier_cap=row[7],
            client_id=row[8],
            revoked=row[9] is not None,
            team_id=row[10] if len(row) > 10 else None,
            team_name=team_name,
            budget_windows=windows,
            metadata=parsed,
            expires_at=expires_at,
        )

    def list(self) -> list[VirtualKey]:
        if not self.enabled:
            return []
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                "SELECT v.key_id, v.name, v.prefix, v.daily_budget_usd, v.monthly_budget_usd,"
                " v.rpm, v.tpm, v.tier_cap, v.client_id, v.revoked_at, v.team_id,"
                " v.budget_windows_json, v.metadata_json, t.name, v.expires_at"
                " FROM virtual_keys v"
                " LEFT JOIN teams t ON t.team_id = v.team_id"
                " ORDER BY v.created_at DESC"
            ).fetchall()
        return [
            self._key_from_row(
                r[:12],
                team_name=r[13],
                metadata=_parse_metadata(r[12]),
                expires_at=r[14],
            )
            for r in rows
        ]

    def resolve(self, plaintext: str) -> VirtualKey | None:
        if not self.enabled or not plaintext:
            return None
        digest = self._hash(plaintext)
        with self._lock, self._connect() as conn:
            row = conn.execute(
                "SELECT v.key_id, v.name, v.prefix, v.daily_budget_usd, v.monthly_budget_usd,"
                " v.rpm, v.tpm, v.tier_cap, v.client_id, v.revoked_at, v.team_id,"
                " v.budget_windows_json, v.metadata_json, t.name, v.expires_at"
                " FROM virtual_keys v"
                " LEFT JOIN teams t ON t.team_id = v.team_id"
                " WHERE v.key_hash = ?",
                (digest,),
            ).fetchone()
        if row is None or row[9] is not None:
            return None
        return self._key_from_row(
            row[:12],
            team_name=row[13],
            metadata=_parse_metadata(row[12]),
            expires_at=row[14],
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
            conn.execute("INSERT INTO key_hits (key_id, ts) VALUES (?, ?)", (key.key_id, now))
            return True

    def to_dict(self, key: VirtualKey) -> dict[str, Any]:
        return {
            "key_id": key.key_id,
            "name": key.name,
            "prefix": key.prefix,
            "daily_budget_usd": key.daily_budget_usd,
            "monthly_budget_usd": key.monthly_budget_usd,
            "rpm": key.rpm,
            "tpm": key.tpm,
            "tier_cap": key.tier_cap,
            "client_id": key.client_id,
            "revoked": key.revoked,
            "team_id": key.team_id,
            "team": key.team_name,
            "budget_windows": [w.as_dict() for w in key.budget_windows],
            "expires_at": key.expires_at,
            "status": key.status(),
        }

    def report_by_team(self, clients: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Roll per-client ledger rows up to the team that owns the key."""
        if not self.enabled:
            return []
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                "SELECT v.key_id, v.client_id, t.name FROM virtual_keys v"
                " JOIN teams t ON t.team_id = v.team_id"
            ).fetchall()
        owner: dict[str, str] = {}
        for key_id, client_id, team_name in rows:
            owner[key_id] = team_name
            if client_id:
                owner[client_id] = team_name
        teams: dict[str, dict[str, Any]] = {}
        for entry in clients:
            team_name = owner.get(entry.get("client_id") or "")
            if not team_name:
                continue
            bucket = teams.setdefault(
                team_name,
                {
                    "team": team_name,
                    "requests": 0,
                    "cache_hits": 0,
                    "local_requests": 0,
                    "frontier_requests": 0,
                    "estimated_saved_usd": 0.0,
                },
            )
            for field_name in (
                "requests",
                "cache_hits",
                "local_requests",
                "frontier_requests",
                "estimated_saved_usd",
            ):
                bucket[field_name] += entry.get(field_name, 0)
        for bucket in teams.values():
            bucket["estimated_saved_usd"] = round(float(bucket["estimated_saved_usd"]), 4)
        return sorted(teams.values(), key=lambda item: -item["requests"])


def _parse_metadata(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}
