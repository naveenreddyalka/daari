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

from daari.auth.model_access import coerce_names, decode_names, encode_names

_UNSET = object()

_RELATIVE_EXPIRY = re.compile(r"^(\d+)([mhd])$")
_NEVER_EXPIRES = {"", "never", "none", "0"}

CACHE_SCOPES = ("global", "team", "key")
_CACHE_SCOPE_RANK = {"global": 0, "team": 1, "key": 2}


def coerce_cache_scope(value: str | None) -> str:
    """Read path: unknown or empty values stay ``global`` so old rows keep working."""
    text = (value or "global").strip().lower()
    if text in _CACHE_SCOPE_RANK:
        return text
    return "global"


def normalize_cache_scope(value: str | None) -> str:
    """Write path: reject anything other than global, team, or key."""
    text = (value or "global").strip().lower() or "global"
    if text not in _CACHE_SCOPE_RANK:
        raise ValueError(
            f"cache_scope must be one of {', '.join(CACHE_SCOPES)} (got {value!r})"
        )
    return text


def coerce_priority(value: str | None) -> str:
    """Read path for admission priority (#848)."""
    from daari.auth.rate_limit import normalize_priority

    return normalize_priority(value)


def effective_cache_scope(*scopes: str | None) -> str:
    """Most isolated scope wins: key > team > global.

    A confidential team stays isolated even when a member key leaves the
    default. A key can tighten further to per-key isolation.
    """
    best = "global"
    for scope in scopes:
        current = coerce_cache_scope(scope)
        if _CACHE_SCOPE_RANK[current] > _CACHE_SCOPE_RANK[best]:
            best = current
    return best


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


def grace_from(raw: str | None, *, now: datetime | None = None) -> str:
    """Grace window for key rotation (#377). Default 24h; `0` / `0h` = immediate."""
    current = now if now is not None else datetime.now(timezone.utc)
    value = (raw if raw is not None else "24h").strip().lower() or "24h"
    if value in {"0", "0m", "0h", "0d"}:
        return current.isoformat()
    match = _RELATIVE_EXPIRY.match(value)
    if match:
        amount, unit = int(match.group(1)), match.group(2)
        if amount <= 0:
            return current.isoformat()
        delta = {
            "m": timedelta(minutes=amount),
            "h": timedelta(hours=amount),
            "d": timedelta(days=amount),
        }
        return (current + delta[unit]).isoformat()
    # Fall back to expiry_from for ISO deadlines; never-tokens become immediate.
    parsed = expiry_from(value, now=current)
    if parsed is None:
        return current.isoformat()
    return parsed


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
    created_at TEXT NOT NULL,
    region_pin TEXT,
    rpm INTEGER NOT NULL DEFAULT 0,
    tpm INTEGER NOT NULL DEFAULT 0,
    rpd INTEGER NOT NULL DEFAULT 0,
    allowed_models_json TEXT,
    model_groups_json TEXT,
    cache_scope TEXT NOT NULL DEFAULT 'global',
    priority TEXT NOT NULL DEFAULT 'normal'
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
    rpd INTEGER NOT NULL DEFAULT 0,
    tier_cap TEXT,
    client_id TEXT,
    team_id TEXT,
    budget_windows_json TEXT NOT NULL DEFAULT '[]',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    user_daily_usd_cap REAL NOT NULL DEFAULT 0,
    allowed_models_json TEXT,
    model_groups_json TEXT,
    cache_scope TEXT NOT NULL DEFAULT 'global',
    priority TEXT NOT NULL DEFAULT 'normal'
);
CREATE TABLE IF NOT EXISTS key_hits (
    key_id TEXT NOT NULL,
    ts REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_key_hits_key_ts ON key_hits(key_id, ts);
"""

# Versioned keys/teams backup document (#548). Bump when the export shape changes.
KEYS_EXPORT_SCHEMA = 1


@dataclass(frozen=True)
class BudgetWindow:
    duration: str
    max_usd: float
    rollover: bool = False
    rollover_cap_multiple: float = 2.0
    # 0 = unlimited. Counts non-cache requests (local + frontier) (#467).
    max_requests: int = 0

    def as_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "duration": self.duration,
            "max_usd": float(self.max_usd),
        }
        if self.max_requests > 0:
            payload["max_requests"] = int(self.max_requests)
        if self.rollover:
            payload["rollover"] = True
            payload["rollover_cap_multiple"] = float(self.rollover_cap_multiple)
        return payload


@dataclass(frozen=True)
class Team:
    team_id: str
    name: str
    budget_windows: tuple[BudgetWindow, ...] = ()
    region_pin: str | None = None
    # Aggregate ceilings across every key on the team (0 = unlimited) (#546).
    rpm: int = 0
    tpm: int = 0
    # Requests per UTC calendar day across member keys (0 = unlimited) (#717).
    rpd: int = 0
    # Model allowlist (#708). None = unrestricted; empty = deny all.
    allowed_models: tuple[str, ...] | None = None
    model_groups: tuple[str, ...] | None = None
    # Cache isolation (#768). global shares the org cache; team / key narrow it.
    cache_scope: str = "global"
    # In-flight admission class (#848). high | normal | low.
    priority: str = "normal"


@dataclass(frozen=True)
class VirtualKey:
    key_id: str
    name: str
    prefix: str
    daily_budget_usd: float = 0.0
    monthly_budget_usd: float = 0.0
    rpm: int = 0
    tpm: int = 0
    # Requests per UTC calendar day (0 = unlimited) (#717).
    rpd: int = 0
    tier_cap: str | None = None
    client_id: str | None = None
    revoked: bool = False
    team_id: str | None = None
    team_name: str | None = None
    budget_windows: tuple[BudgetWindow, ...] = field(default_factory=tuple)
    metadata: dict[str, Any] = field(default_factory=dict)
    # ISO-8601 UTC; None = never expires (#331).
    expires_at: str | None = None
    # Pending previous-secret grace deadline after rotate (#377).
    previous_expires_at: str | None = None
    # Per end-user daily L6 cap on this shared key (0 = unlimited) (#410).
    user_daily_usd_cap: float = 0.0
    # L6 residency pin (#466). Empty/None = unrestricted.
    region_pin: str | None = None
    # Model allowlist (#708). None = unrestricted; empty = deny all.
    allowed_models: tuple[str, ...] | None = None
    model_groups: tuple[str, ...] | None = None
    # Cache isolation (#768). global shares the org cache; team / key narrow it.
    cache_scope: str = "global"
    # In-flight admission class (#848). Prefer metadata["priority"]; column mirrors it.
    priority: str = "normal"

    def is_expired(self, now: datetime | None = None) -> bool:
        return _is_past(self.expires_at, now)

    def status(self, now: datetime | None = None) -> str:
        """`revoked` beats `expired` beats `active` — revocation is explicit."""
        if self.revoked:
            return "revoked"
        if self.is_expired(now):
            return "expired"
        return "active"


def admission_priority_for(
    key: VirtualKey | None = None, team: Team | None = None
) -> str:
    """Key priority wins over team; default normal (#848)."""
    if key is not None:
        meta = getattr(key, "metadata", None) or {}
        raw = getattr(key, "priority", None) or meta.get("priority")
        if raw:
            return coerce_priority(str(raw))
    if team is not None:
        raw = getattr(team, "priority", None)
        if raw:
            return coerce_priority(str(raw))
    return "normal"


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
            try:
                max_requests = int(item.get("max_requests") or 0)
            except (TypeError, ValueError):
                max_requests = 0
            if duration and (max_usd > 0 or max_requests > 0):
                rollover = bool(item.get("rollover") or False)
                try:
                    cap = float(item.get("rollover_cap_multiple") or 2.0)
                except (TypeError, ValueError):
                    cap = 2.0
                if cap <= 1.0:
                    cap = 2.0
                out.append(
                    BudgetWindow(
                        duration,
                        max_usd,
                        rollover=rollover,
                        rollover_cap_multiple=cap,
                        max_requests=max(0, max_requests),
                    )
                )
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
        if "previous_key_hash" not in cols:
            conn.execute("ALTER TABLE virtual_keys ADD COLUMN previous_key_hash TEXT")
        if "previous_prefix" not in cols:
            conn.execute("ALTER TABLE virtual_keys ADD COLUMN previous_prefix TEXT")
        if "previous_expires_at" not in cols:
            conn.execute("ALTER TABLE virtual_keys ADD COLUMN previous_expires_at TEXT")
        if "user_daily_usd_cap" not in cols:
            conn.execute(
                "ALTER TABLE virtual_keys ADD COLUMN user_daily_usd_cap REAL NOT NULL DEFAULT 0"
            )
        if "region_pin" not in cols:
            conn.execute("ALTER TABLE virtual_keys ADD COLUMN region_pin TEXT")
        team_cols = {row[1] for row in conn.execute("PRAGMA table_info(teams)")}
        if "region_pin" not in team_cols:
            conn.execute("ALTER TABLE teams ADD COLUMN region_pin TEXT")
        if "rpm" not in team_cols:
            conn.execute("ALTER TABLE teams ADD COLUMN rpm INTEGER NOT NULL DEFAULT 0")
        if "tpm" not in team_cols:
            conn.execute("ALTER TABLE teams ADD COLUMN tpm INTEGER NOT NULL DEFAULT 0")
        if "rpd" not in team_cols:
            conn.execute("ALTER TABLE teams ADD COLUMN rpd INTEGER NOT NULL DEFAULT 0")
        if "allowed_models_json" not in team_cols:
            conn.execute("ALTER TABLE teams ADD COLUMN allowed_models_json TEXT")
        if "model_groups_json" not in team_cols:
            conn.execute("ALTER TABLE teams ADD COLUMN model_groups_json TEXT")
        if "allowed_models_json" not in cols:
            conn.execute("ALTER TABLE virtual_keys ADD COLUMN allowed_models_json TEXT")
        if "model_groups_json" not in cols:
            conn.execute("ALTER TABLE virtual_keys ADD COLUMN model_groups_json TEXT")
        if "rpd" not in cols:
            conn.execute("ALTER TABLE virtual_keys ADD COLUMN rpd INTEGER NOT NULL DEFAULT 0")
        if "cache_scope" not in cols:
            conn.execute(
                "ALTER TABLE virtual_keys ADD COLUMN cache_scope TEXT NOT NULL DEFAULT 'global'"
            )
        if "cache_scope" not in team_cols:
            conn.execute(
                "ALTER TABLE teams ADD COLUMN cache_scope TEXT NOT NULL DEFAULT 'global'"
            )
        if "priority" not in cols:
            conn.execute(
                "ALTER TABLE virtual_keys ADD COLUMN priority TEXT NOT NULL DEFAULT 'normal'"
            )
        if "priority" not in team_cols:
            conn.execute(
                "ALTER TABLE teams ADD COLUMN priority TEXT NOT NULL DEFAULT 'normal'"
            )
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
        region_pin: str | None = None,
        rpm: int = 0,
        tpm: int = 0,
        rpd: int = 0,
        allowed_models: list[str] | tuple[str, ...] | None = None,
        model_groups: list[str] | tuple[str, ...] | None = None,
        cache_scope: str = "global",
        priority: str = "normal",
    ) -> Team:
        if not self.enabled:
            raise RuntimeError("virtual key store is disabled")
        from daari.auth.budgets import coalesce_windows, windows_from_flat

        windows = coalesce_windows(
            list(budget_windows or ())
            or list(windows_from_flat(daily_usd=daily_budget_usd, monthly_usd=monthly_budget_usd))
        )
        pin = (region_pin or "").strip() or None
        team_rpm = max(0, int(rpm))
        team_tpm = max(0, int(tpm))
        team_rpd = max(0, int(rpd))
        models = coerce_names(allowed_models)
        groups = coerce_names(model_groups)
        scope = normalize_cache_scope(cache_scope)
        prio = coerce_priority(priority)
        team_id = secrets.token_hex(8)
        created = datetime.now(timezone.utc).isoformat()
        with self._lock, self._connect() as conn:
            existing = conn.execute(
                "SELECT team_id, budget_windows_json, region_pin, rpm, tpm,"
                " allowed_models_json, model_groups_json, rpd, cache_scope, priority"
                " FROM teams WHERE name = ?",
                (name,),
            ).fetchone()
            if existing:
                return Team(
                    team_id=existing[0],
                    name=name,
                    budget_windows=self._parse_windows(existing[1]),
                    region_pin=existing[2] if len(existing) > 2 else None,
                    rpm=int(existing[3] or 0) if len(existing) > 3 else 0,
                    tpm=int(existing[4] or 0) if len(existing) > 4 else 0,
                    allowed_models=decode_names(existing[5]) if len(existing) > 5 else None,
                    model_groups=decode_names(existing[6]) if len(existing) > 6 else None,
                    rpd=int(existing[7] or 0) if len(existing) > 7 else 0,
                    cache_scope=coerce_cache_scope(existing[8]) if len(existing) > 8 else "global",
                    priority=coerce_priority(existing[9]) if len(existing) > 9 else "normal",
                )
            conn.execute(
                "INSERT INTO teams (team_id, name, budget_windows_json, created_at,"
                " region_pin, rpm, tpm, allowed_models_json, model_groups_json, rpd,"
                " cache_scope, priority)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    team_id,
                    name,
                    self._windows_json(windows),
                    created,
                    pin,
                    team_rpm,
                    team_tpm,
                    encode_names(models),
                    encode_names(groups),
                    team_rpd,
                    scope,
                    prio,
                ),
            )
        return Team(
            team_id=team_id,
            name=name,
            budget_windows=windows,
            region_pin=pin,
            rpm=team_rpm,
            tpm=team_tpm,
            allowed_models=models,
            model_groups=groups,
            rpd=team_rpd,
            cache_scope=scope,
            priority=prio,
        )

    def update_team(
        self,
        team_id: str,
        *,
        budget_windows: list[BudgetWindow] | None = None,
        daily_budget_usd: float = 0.0,
        monthly_budget_usd: float = 0.0,
        region_pin: str | None = None,
        rpm: int | None = None,
        tpm: int | None = None,
        rpd: int | None = None,
        allowed_models: list[str] | tuple[str, ...] | None | object = _UNSET,
        model_groups: list[str] | tuple[str, ...] | None | object = _UNSET,
    ) -> Team:
        """Replace a team's budget windows (#464), optional region_pin (#466), rpm/tpm (#546).

        ``allowed_models`` / ``model_groups`` default to leaving the stored
        allowlist unchanged. Pass ``None`` to clear (no restriction).
        """
        if not self.enabled:
            raise RuntimeError("virtual key store is disabled")
        from daari.auth.budgets import coalesce_windows, windows_from_flat

        windows = coalesce_windows(
            list(budget_windows or ())
            or list(windows_from_flat(daily_usd=daily_budget_usd, monthly_usd=monthly_budget_usd))
        )
        pin = (region_pin or "").strip() or None
        with self._lock, self._connect() as conn:
            row = conn.execute(
                "SELECT name, region_pin, rpm, tpm, allowed_models_json, model_groups_json, rpd"
                " FROM teams WHERE team_id = ?",
                (team_id,),
            ).fetchone()
            if row is None:
                raise KeyError(team_id)
            if region_pin is None:
                pin = row[1]
            team_rpm = max(0, int(rpm)) if rpm is not None else int(row[2] or 0)
            team_tpm = max(0, int(tpm)) if tpm is not None else int(row[3] or 0)
            team_rpd = (
                max(0, int(rpd)) if rpd is not None else int(row[6] or 0) if len(row) > 6 else 0
            )
            models = (
                decode_names(row[4]) if allowed_models is _UNSET else coerce_names(allowed_models)  # type: ignore[arg-type]
            )
            groups = (
                decode_names(row[5]) if model_groups is _UNSET else coerce_names(model_groups)  # type: ignore[arg-type]
            )
            conn.execute(
                "UPDATE teams SET budget_windows_json = ?, region_pin = ?, rpm = ?, tpm = ?,"
                " allowed_models_json = ?, model_groups_json = ?, rpd = ? WHERE team_id = ?",
                (
                    self._windows_json(windows),
                    pin,
                    team_rpm,
                    team_tpm,
                    encode_names(models),
                    encode_names(groups),
                    team_rpd,
                    team_id,
                ),
            )
        return Team(
            team_id=team_id,
            name=row[0],
            budget_windows=windows,
            region_pin=pin,
            rpm=team_rpm,
            tpm=team_tpm,
            allowed_models=models,
            model_groups=groups,
            rpd=team_rpd,
        )

    def get_team(self, team_id: str | None = None, *, name: str | None = None) -> Team | None:
        if not self.enabled or (not team_id and not name):
            return None
        with self._lock, self._connect() as conn:
            if team_id:
                row = conn.execute(
                    "SELECT team_id, name, budget_windows_json, region_pin, rpm, tpm,"
                    " allowed_models_json, model_groups_json, rpd, cache_scope"
                    " FROM teams WHERE team_id = ?",
                    (team_id,),
                ).fetchone()
            else:
                row = conn.execute(
                    "SELECT team_id, name, budget_windows_json, region_pin, rpm, tpm,"
                    " allowed_models_json, model_groups_json, rpd, cache_scope"
                    " FROM teams WHERE name = ?",
                    (name,),
                ).fetchone()
        if row is None:
            return None
        return Team(
            team_id=row[0],
            name=row[1],
            budget_windows=self._parse_windows(row[2]),
            region_pin=row[3] if len(row) > 3 else None,
            rpm=int(row[4] or 0) if len(row) > 4 else 0,
            tpm=int(row[5] or 0) if len(row) > 5 else 0,
            allowed_models=decode_names(row[6]) if len(row) > 6 else None,
            model_groups=decode_names(row[7]) if len(row) > 7 else None,
            rpd=int(row[8] or 0) if len(row) > 8 else 0,
            cache_scope=coerce_cache_scope(row[9]) if len(row) > 9 else "global",
        )

    def list_teams(self) -> list[Team]:
        """All teams with budget/rate metadata (#616)."""
        if not self.enabled:
            return []
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                "SELECT team_id, name, budget_windows_json, region_pin, rpm, tpm,"
                " allowed_models_json, model_groups_json, rpd, cache_scope"
                " FROM teams ORDER BY created_at ASC, team_id ASC"
            ).fetchall()
        return [
            Team(
                team_id=row[0],
                name=row[1],
                budget_windows=self._parse_windows(row[2]),
                region_pin=row[3] if len(row) > 3 else None,
                rpm=int(row[4] or 0) if len(row) > 4 else 0,
                tpm=int(row[5] or 0) if len(row) > 5 else 0,
                allowed_models=decode_names(row[6]) if len(row) > 6 else None,
                model_groups=decode_names(row[7]) if len(row) > 7 else None,
                rpd=int(row[8] or 0) if len(row) > 8 else 0,
                cache_scope=coerce_cache_scope(row[9]) if len(row) > 9 else "global",
            )
            for row in rows
        ]

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
        rpd: int = 0,
        tier_cap: str | None = None,
        client_id: str | None = None,
        team: str | None = None,
        budget_windows: list[BudgetWindow] | None = None,
        metadata: dict[str, Any] | None = None,
        expires_at: str | None = None,
        user_daily_usd_cap: float = 0.0,
        region_pin: str | None = None,
        allowed_models: list[str] | tuple[str, ...] | None = None,
        model_groups: list[str] | tuple[str, ...] | None = None,
        cache_scope: str = "global",
        priority: str = "normal",
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
        from daari.auth.budgets import coalesce_windows

        windows = coalesce_windows(
            list(budget_windows or ())
            + list(windows_from_flat(daily_usd=daily_budget_usd, monthly_usd=monthly_budget_usd))
        )
        meta = dict(metadata or {})
        pin = (region_pin or "").strip() or None
        if pin:
            meta["region_pin"] = pin
        prio = coerce_priority(priority)
        if "priority" in meta or priority != "normal":
            meta["priority"] = prio
        models = coerce_names(allowed_models)
        groups = coerce_names(model_groups)
        scope = normalize_cache_scope(cache_scope)
        with self._lock, self._connect() as conn:
            conn.execute(
                "INSERT INTO virtual_keys (key_hash, key_id, name, prefix, created_at,"
                " daily_budget_usd, monthly_budget_usd, rpm, tpm, tier_cap, client_id,"
                " team_id, budget_windows_json, metadata_json, expires_at, user_daily_usd_cap,"
                " region_pin, allowed_models_json, model_groups_json, rpd, cache_scope,"
                " priority)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
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
                    json.dumps(meta),
                    expires_at,
                    float(user_daily_usd_cap),
                    pin,
                    encode_names(models),
                    encode_names(groups),
                    max(0, int(rpd)),
                    scope,
                    prio,
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
                rpd=max(0, int(rpd)),
                tier_cap=tier_cap,
                client_id=client_id,
                team_id=team_row.team_id if team_row else None,
                team_name=team_row.name if team_row else None,
                budget_windows=windows,
                metadata=meta,
                expires_at=expires_at,
                user_daily_usd_cap=float(user_daily_usd_cap),
                region_pin=pin,
                allowed_models=models,
                model_groups=groups,
                cache_scope=scope,
                priority=prio,
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
        user_daily_usd_cap: float | None = None,
    ) -> bool:
        if not self.enabled:
            return False
        from daari.auth.budgets import coalesce_windows, windows_from_flat

        team_row = self.create_team(team) if team else None
        windows = coalesce_windows(
            list(budget_windows or ())
            + list(windows_from_flat(daily_usd=daily_budget_usd, monthly_usd=monthly_budget_usd))
        )
        with self._lock, self._connect() as conn:
            if user_daily_usd_cap is None:
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
            else:
                cur = conn.execute(
                    "UPDATE virtual_keys SET daily_budget_usd = ?, monthly_budget_usd = ?,"
                    " rpm = ?, tpm = ?, tier_cap = ?, team_id = ?, budget_windows_json = ?,"
                    " metadata_json = ?, user_daily_usd_cap = ?"
                    " WHERE key_id = ? AND revoked_at IS NULL",
                    (
                        float(daily_budget_usd),
                        float(monthly_budget_usd),
                        int(rpm),
                        int(tpm),
                        tier_cap,
                        team_row.team_id if team_row else None,
                        self._windows_json(windows),
                        json.dumps(metadata or {}),
                        float(user_daily_usd_cap),
                        key_id,
                    ),
                )
            return cur.rowcount > 0

    def update_rpd(self, key_id: str, rpd: int) -> bool:
        """Set a key's calendar-day request cap. ``0`` means unlimited (#717)."""
        if not self.enabled:
            return False
        with self._lock, self._connect() as conn:
            cur = conn.execute(
                "UPDATE virtual_keys SET rpd = ? WHERE key_id = ? AND revoked_at IS NULL",
                (max(0, int(rpd)), key_id),
            )
            return cur.rowcount > 0

    def update_model_access(
        self,
        key_id: str,
        *,
        allowed_models: list[str] | tuple[str, ...] | None | object = _UNSET,
        model_groups: list[str] | tuple[str, ...] | None | object = _UNSET,
    ) -> bool:
        """Replace a key's model allowlist. Omitted sides are left unchanged (#708)."""
        if not self.enabled:
            return False
        with self._lock, self._connect() as conn:
            row = conn.execute(
                "SELECT allowed_models_json, model_groups_json FROM virtual_keys"
                " WHERE key_id = ? AND revoked_at IS NULL",
                (key_id,),
            ).fetchone()
            if row is None:
                return False
            models = (
                decode_names(row[0]) if allowed_models is _UNSET else coerce_names(allowed_models)
            )  # type: ignore[arg-type]
            groups = decode_names(row[1]) if model_groups is _UNSET else coerce_names(model_groups)  # type: ignore[arg-type]
            cur = conn.execute(
                "UPDATE virtual_keys SET allowed_models_json = ?, model_groups_json = ?"
                " WHERE key_id = ? AND revoked_at IS NULL",
                (encode_names(models), encode_names(groups), key_id),
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

    def rotate(
        self,
        key_id: str,
        *,
        grace: str | None = "24h",
        now: datetime | None = None,
    ) -> CreatedKey:
        """Mint a new secret for the same key identity with an overlap window (#377)."""
        if not self.enabled:
            raise RuntimeError("virtual key store is disabled")
        current = now if now is not None else datetime.now(timezone.utc)
        grace_until = grace_from(grace, now=current)
        plaintext = f"dk_{secrets.token_urlsafe(32)}"
        new_hash = self._hash(plaintext)
        new_prefix = plaintext[:10]
        with self._lock, self._connect() as conn:
            row = conn.execute(
                "SELECT key_hash, prefix, name, daily_budget_usd, monthly_budget_usd,"
                " rpm, tpm, tier_cap, client_id, team_id, budget_windows_json,"
                " metadata_json, expires_at, user_daily_usd_cap, rpd"
                " FROM virtual_keys WHERE key_id = ? AND revoked_at IS NULL",
                (key_id,),
            ).fetchone()
            if row is None:
                raise KeyError(key_id)
            (
                old_hash,
                old_prefix,
                name,
                daily,
                monthly,
                rpm,
                tpm,
                tier_cap,
                client_id,
                team_id,
                windows_json,
                metadata_json,
                expires_at,
                user_daily_usd_cap,
            ) = row[:14]
            rpd = int(row[14] or 0) if len(row) > 14 else 0
            conn.execute(
                "UPDATE virtual_keys SET key_hash = ?, prefix = ?,"
                " previous_key_hash = ?, previous_prefix = ?, previous_expires_at = ?"
                " WHERE key_id = ?",
                (new_hash, new_prefix, old_hash, old_prefix, grace_until, key_id),
            )
            team_name = None
            if team_id:
                trow = conn.execute(
                    "SELECT name FROM teams WHERE team_id = ?", (team_id,)
                ).fetchone()
                team_name = trow[0] if trow else None
        windows = self._parse_windows(windows_json)
        if not windows:
            from daari.auth.budgets import windows_from_flat

            windows = windows_from_flat(
                daily_usd=float(daily or 0), monthly_usd=float(monthly or 0)
            )
        return CreatedKey(
            key=VirtualKey(
                key_id=key_id,
                name=name,
                prefix=new_prefix,
                daily_budget_usd=float(daily or 0),
                monthly_budget_usd=float(monthly or 0),
                rpm=int(rpm or 0),
                tpm=int(tpm or 0),
                rpd=rpd,
                tier_cap=tier_cap,
                client_id=client_id,
                team_id=team_id,
                team_name=team_name,
                budget_windows=windows,
                metadata=_parse_metadata(metadata_json),
                expires_at=expires_at,
                previous_expires_at=grace_until,
                user_daily_usd_cap=float(user_daily_usd_cap or 0),
            ),
            plaintext=plaintext,
        )

    def _key_from_row(
        self,
        row: tuple[Any, ...],
        *,
        team_name: str | None = None,
        metadata: dict[str, Any] | None = None,
        expires_at: str | None = None,
        previous_expires_at: str | None = None,
        user_daily_usd_cap: float = 0.0,
        allowed_models: tuple[str, ...] | None = None,
        model_groups: tuple[str, ...] | None = None,
        rpd: int = 0,
        cache_scope: str = "global",
    ) -> VirtualKey:
        windows = self._parse_windows(row[11] if len(row) > 11 else None)
        if not windows:
            from daari.auth.budgets import windows_from_flat

            windows = windows_from_flat(
                daily_usd=float(row[3] or 0), monthly_usd=float(row[4] or 0)
            )
        parsed = metadata or {}
        pin = None
        if isinstance(parsed, dict) and parsed.get("region_pin"):
            pin = str(parsed["region_pin"]).strip() or None
        if pin is None and len(row) > 12:
            # Prefer explicit column when present (list/resolve SELECTs).
            pass
        return VirtualKey(
            key_id=row[0],
            name=row[1],
            prefix=row[2],
            daily_budget_usd=row[3],
            monthly_budget_usd=row[4],
            rpm=row[5],
            tpm=row[6],
            rpd=int(rpd or 0),
            tier_cap=row[7],
            client_id=row[8],
            revoked=row[9] is not None,
            team_id=row[10] if len(row) > 10 else None,
            team_name=team_name,
            budget_windows=windows,
            metadata=parsed,
            expires_at=expires_at,
            previous_expires_at=previous_expires_at,
            user_daily_usd_cap=float(user_daily_usd_cap or 0),
            region_pin=pin,
            allowed_models=allowed_models,
            model_groups=model_groups,
            cache_scope=coerce_cache_scope(cache_scope),
            priority=coerce_priority(
                (parsed.get("priority") if isinstance(parsed, dict) else None)
            ),
        )

    def list(self) -> list[VirtualKey]:
        if not self.enabled:
            return []
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                "SELECT v.key_id, v.name, v.prefix, v.daily_budget_usd, v.monthly_budget_usd,"
                " v.rpm, v.tpm, v.tier_cap, v.client_id, v.revoked_at, v.team_id,"
                " v.budget_windows_json, v.metadata_json, t.name, v.expires_at,"
                " v.previous_expires_at, v.user_daily_usd_cap,"
                " v.allowed_models_json, v.model_groups_json, v.rpd, v.cache_scope"
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
                previous_expires_at=r[15],
                user_daily_usd_cap=float(r[16] or 0),
                allowed_models=decode_names(r[17]) if len(r) > 17 else None,
                model_groups=decode_names(r[18]) if len(r) > 18 else None,
                rpd=int(r[19] or 0) if len(r) > 19 else 0,
                cache_scope=coerce_cache_scope(r[20]) if len(r) > 20 else "global",
            )
            for r in rows
        ]

    def resolve(self, plaintext: str, *, now: datetime | None = None) -> VirtualKey | None:
        if not self.enabled or not plaintext:
            return None
        digest = self._hash(plaintext)
        with self._lock, self._connect() as conn:
            row = conn.execute(
                "SELECT v.key_id, v.name, v.prefix, v.daily_budget_usd, v.monthly_budget_usd,"
                " v.rpm, v.tpm, v.tier_cap, v.client_id, v.revoked_at, v.team_id,"
                " v.budget_windows_json, v.metadata_json, t.name, v.expires_at,"
                " v.previous_expires_at, v.user_daily_usd_cap, v.key_hash, v.previous_key_hash,"
                " v.allowed_models_json, v.model_groups_json, v.rpd, v.cache_scope"
                " FROM virtual_keys v"
                " LEFT JOIN teams t ON t.team_id = v.team_id"
                " WHERE v.key_hash = ? OR v.previous_key_hash = ?",
                (digest, digest),
            ).fetchone()
        if row is None or row[9] is not None:
            return None
        current_hash, previous_hash = row[17], row[18]
        expires_at = row[14]
        previous_expires_at = row[15]
        # Old secret after grace: surface as expired via expires_at so middleware
        # reuses the #331 key_expired path (and one budget identity).
        if previous_hash and digest == previous_hash:
            expires_at = previous_expires_at
        return self._key_from_row(
            row[:12],
            team_name=row[13],
            metadata=_parse_metadata(row[12]),
            expires_at=expires_at,
            previous_expires_at=previous_expires_at if digest == current_hash else None,
            user_daily_usd_cap=float(row[16] or 0),
            allowed_models=decode_names(row[19]) if len(row) > 19 else None,
            model_groups=decode_names(row[20]) if len(row) > 20 else None,
            rpd=int(row[21] or 0) if len(row) > 21 else 0,
            cache_scope=coerce_cache_scope(row[22]) if len(row) > 22 else "global",
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
            "rpd": key.rpd,
            "tier_cap": key.tier_cap,
            "client_id": key.client_id,
            "revoked": key.revoked,
            "team_id": key.team_id,
            "team": key.team_name,
            "region_pin": key.region_pin,
            "allowed_models": list(key.allowed_models) if key.allowed_models is not None else None,
            "model_groups": list(key.model_groups) if key.model_groups is not None else None,
            "budget_windows": [w.as_dict() for w in key.budget_windows],
            "expires_at": key.expires_at,
            "previous_expires_at": key.previous_expires_at,
            "user_daily_usd_cap": key.user_daily_usd_cap,
            "status": key.status(),
            "cache_scope": key.cache_scope,
        }

    def report_by_team(self, clients: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Roll per-client ledger rows up to the team that owns the key."""
        if not self.enabled:
            return []
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                "SELECT v.key_id, v.client_id, t.name, t.rpm, t.tpm FROM virtual_keys v"
                " JOIN teams t ON t.team_id = v.team_id"
            ).fetchall()
        owner: dict[str, tuple[str, int, int]] = {}
        for key_id, client_id, team_name, team_rpm, team_tpm in rows:
            meta = (team_name, int(team_rpm or 0), int(team_tpm or 0))
            owner[key_id] = meta
            if client_id:
                owner[client_id] = meta
        teams: dict[str, dict[str, Any]] = {}
        for entry in clients:
            meta = owner.get(entry.get("client_id") or "")
            if not meta:
                continue
            team_name, team_rpm, team_tpm = meta
            bucket = teams.setdefault(
                team_name,
                {
                    "team": team_name,
                    "requests": 0,
                    "cache_hits": 0,
                    "local_requests": 0,
                    "frontier_requests": 0,
                    "estimated_saved_usd": 0.0,
                    "rpm": team_rpm,
                    "tpm": team_tpm,
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

    def export_document(self) -> dict[str, Any]:
        """Versioned teams+keys snapshot; hashes only, never plaintext (#548)."""
        if not self.enabled:
            raise RuntimeError("virtual key store is disabled")
        with self._lock, self._connect() as conn:
            team_rows = conn.execute(
                "SELECT team_id, name, budget_windows_json, created_at, region_pin, rpm, tpm,"
                " allowed_models_json, model_groups_json, rpd"
                " FROM teams ORDER BY created_at ASC, team_id ASC"
            ).fetchall()
            key_rows = conn.execute(
                "SELECT key_hash, key_id, name, prefix, created_at, revoked_at, expires_at,"
                " daily_budget_usd, monthly_budget_usd, rpm, tpm, tier_cap, client_id,"
                " team_id, budget_windows_json, metadata_json, user_daily_usd_cap,"
                " previous_key_hash, previous_prefix, previous_expires_at, region_pin,"
                " allowed_models_json, model_groups_json, rpd"
                " FROM virtual_keys ORDER BY created_at ASC, key_id ASC"
            ).fetchall()
        teams = [
            {
                "team_id": row[0],
                "name": row[1],
                "budget_windows": [w.as_dict() for w in self._parse_windows(row[2])],
                "created_at": row[3],
                "region_pin": row[4],
                "rpm": int(row[5] or 0),
                "tpm": int(row[6] or 0),
                "allowed_models": list(decode_names(row[7]) or ())
                if len(row) > 7 and row[7] is not None
                else None,
                "model_groups": list(decode_names(row[8]) or ())
                if len(row) > 8 and row[8] is not None
                else None,
                "rpd": int(row[9] or 0) if len(row) > 9 else 0,
            }
            for row in team_rows
        ]
        keys = []
        for row in key_rows:
            keys.append(
                {
                    "key_hash": row[0],
                    "key_id": row[1],
                    "name": row[2],
                    "prefix": row[3],
                    "created_at": row[4],
                    "revoked_at": row[5],
                    "expires_at": row[6],
                    "daily_budget_usd": float(row[7] or 0),
                    "monthly_budget_usd": float(row[8] or 0),
                    "rpm": int(row[9] or 0),
                    "tpm": int(row[10] or 0),
                    "tier_cap": row[11],
                    "client_id": row[12],
                    "team_id": row[13],
                    "budget_windows": [w.as_dict() for w in self._parse_windows(row[14])],
                    "metadata": _parse_metadata(row[15]),
                    "user_daily_usd_cap": float(row[16] or 0),
                    "previous_key_hash": row[17],
                    "previous_prefix": row[18],
                    "previous_expires_at": row[19],
                    "region_pin": row[20],
                    "allowed_models": list(decode_names(row[21]) or ())
                    if len(row) > 21 and row[21] is not None
                    else None,
                    "model_groups": list(decode_names(row[22]) or ())
                    if len(row) > 22 and row[22] is not None
                    else None,
                    "rpd": int(row[23] or 0) if len(row) > 23 else 0,
                }
            )
        return {
            "schema": KEYS_EXPORT_SCHEMA,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "teams": teams,
            "keys": keys,
        }

    def import_document(
        self,
        document: dict[str, Any],
        *,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """Upsert teams/keys by id. Refuses unknown schema versions (#548)."""
        if not self.enabled:
            raise RuntimeError("virtual key store is disabled")
        if not isinstance(document, dict):
            raise ValueError("export document must be a JSON object")
        schema = document.get("schema")
        if schema != KEYS_EXPORT_SCHEMA:
            raise ValueError(
                f"unsupported keys export schema {schema!r}; expected {KEYS_EXPORT_SCHEMA}"
            )
        teams_in = list(document.get("teams") or [])
        keys_in = list(document.get("keys") or [])
        summary: dict[str, Any] = {
            "dry_run": dry_run,
            "teams": {"created": 0, "updated": 0, "skipped": 0},
            "keys": {"created": 0, "updated": 0, "skipped": 0},
        }

        def _windows_payload(raw: Any) -> list[BudgetWindow]:
            if not raw:
                return []
            if isinstance(raw, str):
                return list(self._parse_windows(raw))
            if isinstance(raw, list):
                return list(self._parse_windows(json.dumps(raw)))
            return []

        with self._lock, self._connect() as conn:
            for team in teams_in:
                team_id = str(team.get("team_id") or "")
                name = str(team.get("name") or "")
                if not team_id or not name:
                    raise ValueError("team entries require team_id and name")
                windows = _windows_payload(team.get("budget_windows"))
                pin = (team.get("region_pin") or None) or None
                if isinstance(pin, str):
                    pin = pin.strip() or None
                rpm = max(0, int(team.get("rpm") or 0))
                tpm = max(0, int(team.get("tpm") or 0))
                rpd = max(0, int(team.get("rpd") or 0))
                team_models = decode_names(team.get("allowed_models"))
                team_groups = decode_names(team.get("model_groups"))
                created_at = team.get("created_at") or datetime.now(timezone.utc).isoformat()
                existing = conn.execute(
                    "SELECT name, budget_windows_json, region_pin, rpm, tpm, created_at,"
                    " allowed_models_json, model_groups_json, rpd"
                    " FROM teams WHERE team_id = ?",
                    (team_id,),
                ).fetchone()
                desired = (
                    name,
                    self._windows_json(windows),
                    pin,
                    rpm,
                    tpm,
                    encode_names(team_models),
                    encode_names(team_groups),
                    rpd,
                )
                if existing is None:
                    summary["teams"]["created"] += 1
                    if not dry_run:
                        conn.execute(
                            "INSERT INTO teams (team_id, name, budget_windows_json,"
                            " created_at, region_pin, rpm, tpm, allowed_models_json,"
                            " model_groups_json, rpd) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                            (team_id, *desired[:2], created_at, *desired[2:]),
                        )
                else:
                    current = (
                        existing[0],
                        existing[1] or "[]",
                        existing[2],
                        int(existing[3] or 0),
                        int(existing[4] or 0),
                    )
                    # Normalize window JSON for comparison.
                    current_norm = (
                        current[0],
                        self._windows_json(self._parse_windows(current[1])),
                        current[2],
                        current[3],
                        current[4],
                        decode_names(existing[6]) if len(existing) > 6 else None,
                        decode_names(existing[7]) if len(existing) > 7 else None,
                        int(existing[8] or 0) if len(existing) > 8 else 0,
                    )
                    desired_norm = (
                        desired[0],
                        self._windows_json(windows),
                        desired[2],
                        desired[3],
                        desired[4],
                        team_models,
                        team_groups,
                        rpd,
                    )
                    if current_norm == desired_norm:
                        summary["teams"]["skipped"] += 1
                    else:
                        summary["teams"]["updated"] += 1
                        if not dry_run:
                            conn.execute(
                                "UPDATE teams SET name = ?, budget_windows_json = ?,"
                                " region_pin = ?, rpm = ?, tpm = ?,"
                                " allowed_models_json = ?, model_groups_json = ?, rpd = ?"
                                " WHERE team_id = ?",
                                (*desired, team_id),
                            )

            for key in keys_in:
                key_id = str(key.get("key_id") or "")
                key_hash = str(key.get("key_hash") or "")
                name = str(key.get("name") or "")
                prefix = str(key.get("prefix") or "")
                if not key_id or not key_hash or not name or not prefix:
                    raise ValueError("key entries require key_id, key_hash, name, and prefix")
                windows = _windows_payload(key.get("budget_windows"))
                meta = key.get("metadata") if isinstance(key.get("metadata"), dict) else {}
                region_pin = key.get("region_pin") or None
                if isinstance(region_pin, str):
                    region_pin = region_pin.strip() or None
                key_models = decode_names(key.get("allowed_models"))
                key_groups = decode_names(key.get("model_groups"))
                values = (
                    key_hash,
                    name,
                    prefix,
                    key.get("created_at") or datetime.now(timezone.utc).isoformat(),
                    key.get("revoked_at"),
                    key.get("expires_at"),
                    float(key.get("daily_budget_usd") or 0),
                    float(key.get("monthly_budget_usd") or 0),
                    max(0, int(key.get("rpm") or 0)),
                    max(0, int(key.get("tpm") or 0)),
                    key.get("tier_cap"),
                    key.get("client_id"),
                    key.get("team_id"),
                    self._windows_json(windows),
                    json.dumps(meta),
                    float(key.get("user_daily_usd_cap") or 0),
                    key.get("previous_key_hash"),
                    key.get("previous_prefix"),
                    key.get("previous_expires_at"),
                    region_pin,
                    encode_names(key_models),
                    encode_names(key_groups),
                    max(0, int(key.get("rpd") or 0)),
                )
                existing = conn.execute(
                    "SELECT key_hash, name, prefix, created_at, revoked_at, expires_at,"
                    " daily_budget_usd, monthly_budget_usd, rpm, tpm, tier_cap, client_id,"
                    " team_id, budget_windows_json, metadata_json, user_daily_usd_cap,"
                    " previous_key_hash, previous_prefix, previous_expires_at, region_pin,"
                    " allowed_models_json, model_groups_json, rpd"
                    " FROM virtual_keys WHERE key_id = ?",
                    (key_id,),
                ).fetchone()
                if existing is None:
                    summary["keys"]["created"] += 1
                    if not dry_run:
                        conn.execute(
                            "INSERT INTO virtual_keys (key_hash, key_id, name, prefix,"
                            " created_at, revoked_at, expires_at, daily_budget_usd,"
                            " monthly_budget_usd, rpm, tpm, tier_cap, client_id, team_id,"
                            " budget_windows_json, metadata_json, user_daily_usd_cap,"
                            " previous_key_hash, previous_prefix, previous_expires_at,"
                            " region_pin, allowed_models_json, model_groups_json, rpd)"
                            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,"
                            " ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                            (
                                values[0],
                                key_id,
                                values[1],
                                values[2],
                                values[3],
                                values[4],
                                values[5],
                                values[6],
                                values[7],
                                values[8],
                                values[9],
                                values[10],
                                values[11],
                                values[12],
                                values[13],
                                values[14],
                                values[15],
                                values[16],
                                values[17],
                                values[18],
                                values[19],
                                values[20],
                                values[21],
                                values[22],
                            ),
                        )
                else:
                    current = (
                        existing[0],
                        existing[1],
                        existing[2],
                        existing[4],
                        existing[5],
                        float(existing[6] or 0),
                        float(existing[7] or 0),
                        int(existing[8] or 0),
                        int(existing[9] or 0),
                        existing[10],
                        existing[11],
                        existing[12],
                        self._windows_json(self._parse_windows(existing[13])),
                        json.dumps(_parse_metadata(existing[14]), sort_keys=True),
                        float(existing[15] or 0),
                        existing[16],
                        existing[17],
                        existing[18],
                        existing[19],
                        decode_names(existing[20]) if len(existing) > 20 else None,
                        decode_names(existing[21]) if len(existing) > 21 else None,
                        int(existing[22] or 0) if len(existing) > 22 else 0,
                    )
                    desired_cmp = (
                        values[0],
                        values[1],
                        values[2],
                        values[4],
                        values[5],
                        values[6],
                        values[7],
                        values[8],
                        values[9],
                        values[10],
                        values[11],
                        values[12],
                        self._windows_json(windows),
                        json.dumps(meta, sort_keys=True),
                        values[15],
                        values[16],
                        values[17],
                        values[18],
                        values[19],
                        key_models,
                        key_groups,
                        values[22],
                    )
                    if current == desired_cmp:
                        summary["keys"]["skipped"] += 1
                    else:
                        summary["keys"]["updated"] += 1
                        if not dry_run:
                            conflict = conn.execute(
                                "SELECT key_id FROM virtual_keys"
                                " WHERE key_hash = ? AND key_id != ?",
                                (key_hash, key_id),
                            ).fetchone()
                            if conflict:
                                raise ValueError(
                                    f"key_hash for {key_id} already owned by {conflict[0]}"
                                )
                            conn.execute(
                                "UPDATE virtual_keys SET key_hash = ?, name = ?, prefix = ?,"
                                " revoked_at = ?, expires_at = ?, daily_budget_usd = ?,"
                                " monthly_budget_usd = ?, rpm = ?, tpm = ?, tier_cap = ?,"
                                " client_id = ?, team_id = ?, budget_windows_json = ?,"
                                " metadata_json = ?, user_daily_usd_cap = ?,"
                                " previous_key_hash = ?, previous_prefix = ?,"
                                " previous_expires_at = ?, region_pin = ?,"
                                " allowed_models_json = ?, model_groups_json = ?, rpd = ?"
                                " WHERE key_id = ?",
                                (
                                    values[0],
                                    values[1],
                                    values[2],
                                    values[4],
                                    values[5],
                                    values[6],
                                    values[7],
                                    values[8],
                                    values[9],
                                    values[10],
                                    values[11],
                                    values[12],
                                    values[13],
                                    values[14],
                                    values[15],
                                    values[16],
                                    values[17],
                                    values[18],
                                    values[19],
                                    values[20],
                                    values[21],
                                    values[22],
                                    key_id,
                                ),
                            )
        return summary


def _parse_metadata(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}
