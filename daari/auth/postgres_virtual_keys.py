"""Postgres-backed virtual keys / teams for cross-replica fleets (#544).

Duck-types ``VirtualKeyStore``. DSN is ``observability.postgres_url``.
``memory:<name>`` shares a SQLite file across instances for unit tests.

Per-pod ``key_hits`` RPM sampling stays local (in-process for the postgres
path; Redis rate-limit counters already cover distributed RPM).
"""

from __future__ import annotations

import json
import secrets
import tempfile
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from daari.auth.virtual_keys import (
    BudgetWindow,
    CreatedKey,
    KEYS_EXPORT_SCHEMA,
    Team,
    VirtualKey,
    VirtualKeyStore,
    _parse_metadata,
    expiry_from,
    grace_from,
)

_PG_SCHEMA = """
CREATE TABLE IF NOT EXISTS teams (
    team_id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    budget_windows_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL,
    region_pin TEXT,
    rpm INTEGER NOT NULL DEFAULT 0,
    tpm INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS virtual_keys (
    key_hash TEXT PRIMARY KEY,
    key_id TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    prefix TEXT NOT NULL,
    created_at TEXT NOT NULL,
    revoked_at TEXT,
    expires_at TEXT,
    daily_budget_usd DOUBLE PRECISION NOT NULL DEFAULT 0,
    monthly_budget_usd DOUBLE PRECISION NOT NULL DEFAULT 0,
    rpm INTEGER NOT NULL DEFAULT 0,
    tpm INTEGER NOT NULL DEFAULT 0,
    tier_cap TEXT,
    client_id TEXT,
    team_id TEXT,
    budget_windows_json TEXT NOT NULL DEFAULT '[]',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    user_daily_usd_cap DOUBLE PRECISION NOT NULL DEFAULT 0,
    previous_key_hash TEXT,
    previous_prefix TEXT,
    previous_expires_at TEXT,
    region_pin TEXT
);
"""

_PG_TEAM_MIGRATIONS = (
    "ALTER TABLE teams ADD COLUMN IF NOT EXISTS rpm INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE teams ADD COLUMN IF NOT EXISTS tpm INTEGER NOT NULL DEFAULT 0",
)

_MEMORY_PATHS: dict[str, Path] = {}
_MEMORY_META = threading.Lock()


def _memory_sqlite_path(dsn: str) -> Path:
    with _MEMORY_META:
        if dsn not in _MEMORY_PATHS:
            handle = tempfile.NamedTemporaryFile(
                prefix="daari-vk-", suffix=".sqlite3", delete=False
            )
            handle.close()
            _MEMORY_PATHS[dsn] = Path(handle.name)
        return _MEMORY_PATHS[dsn]


class PostgresVirtualKeyStore:
    """Fleet-shared virtual keys via Postgres (or shared memory: SQLite for tests)."""

    def __init__(self, dsn: str, enabled: bool = True) -> None:
        self.dsn = dsn
        self.path = dsn
        self.enabled = enabled
        self._lock = threading.Lock()
        self._memory = dsn.startswith("memory:")
        # Local RPM sampler — not fleet-shared (#544).
        self._local_hits: dict[str, list[float]] = {}
        self._inner: VirtualKeyStore | None = None
        if self._memory:
            self._inner = VirtualKeyStore(_memory_sqlite_path(dsn), enabled=enabled)
            self.enabled = self._inner.enabled
            return
        if self.enabled:
            try:
                with self._connect() as conn:
                    with conn.cursor() as cur:
                        cur.execute(_PG_SCHEMA)
                        for stmt in _PG_TEAM_MIGRATIONS:
                            cur.execute(stmt)
                    conn.commit()
            except Exception:
                self.enabled = False

    def _connect(self) -> Any:
        try:
            import psycopg
        except ImportError as exc:
            raise RuntimeError(
                "server.virtual_keys.backend=postgres requires psycopg — "
                "pip install 'psycopg[binary]>=3' (or daari[postgres])"
            ) from exc
        return psycopg.connect(self.dsn)

    def _delegate(self) -> VirtualKeyStore | None:
        return self._inner

    # Reuse parsing helpers from the SQLite store.
    _windows_json = staticmethod(VirtualKeyStore._windows_json)
    _parse_windows = staticmethod(VirtualKeyStore._parse_windows)
    _hash = staticmethod(VirtualKeyStore._hash)

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
    ) -> Team:
        if self._inner is not None:
            return self._inner.create_team(
                name,
                budget_windows=budget_windows,
                daily_budget_usd=daily_budget_usd,
                monthly_budget_usd=monthly_budget_usd,
                region_pin=region_pin,
                rpm=rpm,
                tpm=tpm,
            )
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
        team_id = secrets.token_hex(8)
        created = datetime.now(timezone.utc).isoformat()
        with self._lock, self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT team_id, budget_windows_json, region_pin, rpm, tpm"
                    " FROM teams WHERE name = %s",
                    (name,),
                )
                existing = cur.fetchone()
                if existing:
                    return Team(
                        team_id=existing[0],
                        name=name,
                        budget_windows=self._parse_windows(existing[1]),
                        region_pin=existing[2],
                        rpm=int(existing[3] or 0),
                        tpm=int(existing[4] or 0),
                    )
                cur.execute(
                    "INSERT INTO teams (team_id, name, budget_windows_json, created_at,"
                    " region_pin, rpm, tpm) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                    (
                        team_id,
                        name,
                        self._windows_json(windows),
                        created,
                        pin,
                        team_rpm,
                        team_tpm,
                    ),
                )
            conn.commit()
        return Team(
            team_id=team_id,
            name=name,
            budget_windows=windows,
            region_pin=pin,
            rpm=team_rpm,
            tpm=team_tpm,
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
    ) -> Team:
        if self._inner is not None:
            return self._inner.update_team(
                team_id,
                budget_windows=budget_windows,
                daily_budget_usd=daily_budget_usd,
                monthly_budget_usd=monthly_budget_usd,
                region_pin=region_pin,
                rpm=rpm,
                tpm=tpm,
            )
        if not self.enabled:
            raise RuntimeError("virtual key store is disabled")
        from daari.auth.budgets import coalesce_windows, windows_from_flat

        windows = coalesce_windows(
            list(budget_windows or ())
            or list(windows_from_flat(daily_usd=daily_budget_usd, monthly_usd=monthly_budget_usd))
        )
        pin = (region_pin or "").strip() or None
        with self._lock, self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT name, region_pin, rpm, tpm FROM teams WHERE team_id = %s",
                    (team_id,),
                )
                row = cur.fetchone()
                if row is None:
                    raise KeyError(team_id)
                if region_pin is None:
                    pin = row[1]
                team_rpm = max(0, int(rpm)) if rpm is not None else int(row[2] or 0)
                team_tpm = max(0, int(tpm)) if tpm is not None else int(row[3] or 0)
                cur.execute(
                    "UPDATE teams SET budget_windows_json = %s, region_pin = %s,"
                    " rpm = %s, tpm = %s WHERE team_id = %s",
                    (self._windows_json(windows), pin, team_rpm, team_tpm, team_id),
                )
            conn.commit()
        return Team(
            team_id=team_id,
            name=row[0],
            budget_windows=windows,
            region_pin=pin,
            rpm=team_rpm,
            tpm=team_tpm,
        )

    def get_team(self, team_id: str | None = None, *, name: str | None = None) -> Team | None:
        if self._inner is not None:
            return self._inner.get_team(team_id, name=name)
        if not self.enabled or (not team_id and not name):
            return None
        with self._lock, self._connect() as conn:
            with conn.cursor() as cur:
                if team_id:
                    cur.execute(
                        "SELECT team_id, name, budget_windows_json, region_pin, rpm, tpm"
                        " FROM teams WHERE team_id = %s",
                        (team_id,),
                    )
                else:
                    cur.execute(
                        "SELECT team_id, name, budget_windows_json, region_pin, rpm, tpm"
                        " FROM teams WHERE name = %s",
                        (name,),
                    )
                row = cur.fetchone()
        if row is None:
            return None
        return Team(
            team_id=row[0],
            name=row[1],
            budget_windows=self._parse_windows(row[2]),
            region_pin=row[3],
            rpm=int(row[4] or 0),
            tpm=int(row[5] or 0),
        )

    def team_client_ids(self, team_id: str) -> list[str]:
        if self._inner is not None:
            return self._inner.team_client_ids(team_id)
        if not self.enabled:
            return []
        with self._lock, self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT key_id, client_id FROM virtual_keys"
                    " WHERE team_id = %s AND revoked_at IS NULL",
                    (team_id,),
                )
                rows = cur.fetchall()
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
        user_daily_usd_cap: float = 0.0,
        region_pin: str | None = None,
    ) -> CreatedKey:
        if self._inner is not None:
            return self._inner.create(
                name,
                daily_budget_usd=daily_budget_usd,
                monthly_budget_usd=monthly_budget_usd,
                rpm=rpm,
                tpm=tpm,
                tier_cap=tier_cap,
                client_id=client_id,
                team=team,
                budget_windows=budget_windows,
                metadata=metadata,
                expires_at=expires_at,
                user_daily_usd_cap=user_daily_usd_cap,
                region_pin=region_pin,
            )
        if not self.enabled:
            raise RuntimeError("virtual key store is disabled")
        from daari.auth.budgets import coalesce_windows, windows_from_flat

        expires_at = expiry_from(expires_at)
        plaintext = f"dk_{secrets.token_urlsafe(32)}"
        key_id = secrets.token_hex(8)
        prefix = plaintext[:10]
        created = datetime.now(timezone.utc).isoformat()
        team_row = self.create_team(team) if team else None
        windows = coalesce_windows(
            list(budget_windows or ())
            + list(windows_from_flat(daily_usd=daily_budget_usd, monthly_usd=monthly_budget_usd))
        )
        meta = dict(metadata or {})
        pin = (region_pin or "").strip() or None
        if pin:
            meta["region_pin"] = pin
        with self._lock, self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO virtual_keys (key_hash, key_id, name, prefix, created_at,"
                    " daily_budget_usd, monthly_budget_usd, rpm, tpm, tier_cap, client_id,"
                    " team_id, budget_windows_json, metadata_json, expires_at, user_daily_usd_cap,"
                    " region_pin)"
                    " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
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
                    ),
                )
            conn.commit()
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
                metadata=meta,
                expires_at=expires_at,
                user_daily_usd_cap=float(user_daily_usd_cap),
                region_pin=pin,
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
        if self._inner is not None:
            return self._inner.update_limits(
                key_id,
                daily_budget_usd=daily_budget_usd,
                monthly_budget_usd=monthly_budget_usd,
                rpm=rpm,
                tpm=tpm,
                tier_cap=tier_cap,
                team=team,
                budget_windows=budget_windows,
                metadata=metadata,
                user_daily_usd_cap=user_daily_usd_cap,
            )
        if not self.enabled:
            return False
        from daari.auth.budgets import coalesce_windows, windows_from_flat

        team_row = self.create_team(team) if team else None
        windows = coalesce_windows(
            list(budget_windows or ())
            + list(windows_from_flat(daily_usd=daily_budget_usd, monthly_usd=monthly_budget_usd))
        )
        with self._lock, self._connect() as conn:
            with conn.cursor() as cur:
                if user_daily_usd_cap is None:
                    cur.execute(
                        "UPDATE virtual_keys SET daily_budget_usd = %s, monthly_budget_usd = %s,"
                        " rpm = %s, tpm = %s, tier_cap = %s, team_id = %s, budget_windows_json = %s,"
                        " metadata_json = %s WHERE key_id = %s AND revoked_at IS NULL",
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
                    cur.execute(
                        "UPDATE virtual_keys SET daily_budget_usd = %s, monthly_budget_usd = %s,"
                        " rpm = %s, tpm = %s, tier_cap = %s, team_id = %s, budget_windows_json = %s,"
                        " metadata_json = %s, user_daily_usd_cap = %s"
                        " WHERE key_id = %s AND revoked_at IS NULL",
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
                updated = cur.rowcount > 0
            conn.commit()
        return updated

    def revoke(self, key_id: str) -> bool:
        if self._inner is not None:
            return self._inner.revoke(key_id)
        if not self.enabled:
            return False
        with self._lock, self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE virtual_keys SET revoked_at = %s"
                    " WHERE key_id = %s AND revoked_at IS NULL",
                    (datetime.now(timezone.utc).isoformat(), key_id),
                )
                updated = cur.rowcount > 0
            conn.commit()
        return updated

    def rotate(
        self,
        key_id: str,
        *,
        grace: str | None = "24h",
        now: datetime | None = None,
    ) -> CreatedKey:
        if self._inner is not None:
            return self._inner.rotate(key_id, grace=grace, now=now)
        if not self.enabled:
            raise RuntimeError("virtual key store is disabled")
        current = now if now is not None else datetime.now(timezone.utc)
        grace_until = grace_from(grace, now=current)
        plaintext = f"dk_{secrets.token_urlsafe(32)}"
        new_hash = self._hash(plaintext)
        new_prefix = plaintext[:10]
        with self._lock, self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT key_hash, prefix, name, daily_budget_usd, monthly_budget_usd,"
                    " rpm, tpm, tier_cap, client_id, team_id, budget_windows_json,"
                    " metadata_json, expires_at, user_daily_usd_cap"
                    " FROM virtual_keys WHERE key_id = %s AND revoked_at IS NULL",
                    (key_id,),
                )
                row = cur.fetchone()
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
                ) = row
                cur.execute(
                    "UPDATE virtual_keys SET key_hash = %s, prefix = %s,"
                    " previous_key_hash = %s, previous_prefix = %s, previous_expires_at = %s"
                    " WHERE key_id = %s",
                    (new_hash, new_prefix, old_hash, old_prefix, grace_until, key_id),
                )
                team_name = None
                if team_id:
                    cur.execute("SELECT name FROM teams WHERE team_id = %s", (team_id,))
                    trow = cur.fetchone()
                    team_name = trow[0] if trow else None
            conn.commit()
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
    ) -> VirtualKey:
        return VirtualKeyStore._key_from_row(
            self,  # type: ignore[arg-type]
            row,
            team_name=team_name,
            metadata=metadata,
            expires_at=expires_at,
            previous_expires_at=previous_expires_at,
            user_daily_usd_cap=user_daily_usd_cap,
        )

    def list(self) -> list[VirtualKey]:
        if self._inner is not None:
            return self._inner.list()
        if not self.enabled:
            return []
        with self._lock, self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT v.key_id, v.name, v.prefix, v.daily_budget_usd, v.monthly_budget_usd,"
                    " v.rpm, v.tpm, v.tier_cap, v.client_id, v.revoked_at, v.team_id,"
                    " v.budget_windows_json, v.metadata_json, t.name, v.expires_at,"
                    " v.previous_expires_at, v.user_daily_usd_cap"
                    " FROM virtual_keys v"
                    " LEFT JOIN teams t ON t.team_id = v.team_id"
                    " ORDER BY v.created_at DESC"
                )
                rows = cur.fetchall()
        return [
            self._key_from_row(
                r[:12],
                team_name=r[13],
                metadata=_parse_metadata(r[12]),
                expires_at=r[14],
                previous_expires_at=r[15],
                user_daily_usd_cap=float(r[16] or 0),
            )
            for r in rows
        ]

    def resolve(self, plaintext: str, *, now: datetime | None = None) -> VirtualKey | None:
        if self._inner is not None:
            return self._inner.resolve(plaintext, now=now)
        if not self.enabled or not plaintext:
            return None
        digest = self._hash(plaintext)
        with self._lock, self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT v.key_id, v.name, v.prefix, v.daily_budget_usd, v.monthly_budget_usd,"
                    " v.rpm, v.tpm, v.tier_cap, v.client_id, v.revoked_at, v.team_id,"
                    " v.budget_windows_json, v.metadata_json, t.name, v.expires_at,"
                    " v.previous_expires_at, v.user_daily_usd_cap, v.key_hash, v.previous_key_hash"
                    " FROM virtual_keys v"
                    " LEFT JOIN teams t ON t.team_id = v.team_id"
                    " WHERE v.key_hash = %s OR v.previous_key_hash = %s",
                    (digest, digest),
                )
                row = cur.fetchone()
        if row is None or row[9] is not None:
            return None
        current_hash, previous_hash = row[17], row[18]
        expires_at = row[14]
        previous_expires_at = row[15]
        if previous_hash and digest == previous_hash:
            expires_at = previous_expires_at
        return self._key_from_row(
            row[:12],
            team_name=row[13],
            metadata=_parse_metadata(row[12]),
            expires_at=expires_at,
            previous_expires_at=previous_expires_at if digest == current_hash else None,
            user_daily_usd_cap=float(row[16] or 0),
        )

    def check_rpm(self, key: VirtualKey) -> bool:
        """Local RPM sampler — not fleet-shared; use Redis rate limits for fleets."""
        if self._inner is not None:
            return self._inner.check_rpm(key)
        if not self.enabled or key.rpm <= 0:
            return True
        now = time.time()
        window_start = now - 60.0
        with self._lock:
            hits = [ts for ts in self._local_hits.get(key.key_id, []) if ts >= window_start]
            if len(hits) >= key.rpm:
                self._local_hits[key.key_id] = hits
                return False
            hits.append(now)
            self._local_hits[key.key_id] = hits
            return True

    def to_dict(self, key: VirtualKey) -> dict[str, Any]:
        if self._inner is not None:
            return self._inner.to_dict(key)
        return VirtualKeyStore.to_dict(self, key)  # type: ignore[arg-type]

    def report_by_team(self, clients: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if self._inner is not None:
            return self._inner.report_by_team(clients)
        if not self.enabled:
            return []
        with self._lock, self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT v.key_id, v.client_id, t.name, t.rpm, t.tpm FROM virtual_keys v"
                    " JOIN teams t ON t.team_id = v.team_id"
                )
                rows = cur.fetchall()
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
        if self._inner is not None:
            return self._inner.export_document()
        if not self.enabled:
            raise RuntimeError("virtual key store is disabled")
        with self._lock, self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT team_id, name, budget_windows_json, created_at, region_pin, rpm, tpm"
                    " FROM teams ORDER BY created_at ASC, team_id ASC"
                )
                team_rows = cur.fetchall()
                cur.execute(
                    "SELECT key_hash, key_id, name, prefix, created_at, revoked_at, expires_at,"
                    " daily_budget_usd, monthly_budget_usd, rpm, tpm, tier_cap, client_id,"
                    " team_id, budget_windows_json, metadata_json, user_daily_usd_cap,"
                    " previous_key_hash, previous_prefix, previous_expires_at, region_pin"
                    " FROM virtual_keys ORDER BY created_at ASC, key_id ASC"
                )
                key_rows = cur.fetchall()
        # Reuse SQLite assembler via a throwaway store disabled for I/O — build inline.
        teams = [
            {
                "team_id": row[0],
                "name": row[1],
                "budget_windows": [w.as_dict() for w in self._parse_windows(row[2])],
                "created_at": row[3],
                "region_pin": row[4],
                "rpm": int(row[5] or 0),
                "tpm": int(row[6] or 0),
            }
            for row in team_rows
        ]
        keys = [
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
            }
            for row in key_rows
        ]
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
        if self._inner is not None:
            return self._inner.import_document(document, dry_run=dry_run)
        if not self.enabled:
            raise RuntimeError("virtual key store is disabled")
        if not isinstance(document, dict):
            raise ValueError("export document must be a JSON object")
        schema = document.get("schema")
        if schema != KEYS_EXPORT_SCHEMA:
            raise ValueError(
                f"unsupported keys export schema {schema!r}; expected {KEYS_EXPORT_SCHEMA}"
            )
        # Validate + count via SQLite bridge, then upsert into Postgres.
        handle = tempfile.NamedTemporaryFile(
            prefix="daari-vk-import-", suffix=".sqlite3", delete=False
        )
        handle.close()
        path = Path(handle.name)
        try:
            bridge = VirtualKeyStore(path, enabled=True)
            summary = bridge.import_document(document, dry_run=dry_run)
            if dry_run:
                return summary
            doc = bridge.export_document()
            with self._lock, self._connect() as conn:
                with conn.cursor() as cur:
                    for team in doc["teams"]:
                        windows = self._windows_json(
                            self._parse_windows(json.dumps(team.get("budget_windows") or []))
                        )
                        cur.execute(
                            "INSERT INTO teams (team_id, name, budget_windows_json, created_at,"
                            " region_pin, rpm, tpm) VALUES (%s, %s, %s, %s, %s, %s, %s)"
                            " ON CONFLICT (team_id) DO UPDATE SET"
                            " name = EXCLUDED.name,"
                            " budget_windows_json = EXCLUDED.budget_windows_json,"
                            " region_pin = EXCLUDED.region_pin,"
                            " rpm = EXCLUDED.rpm,"
                            " tpm = EXCLUDED.tpm",
                            (
                                team["team_id"],
                                team["name"],
                                windows,
                                team.get("created_at") or datetime.now(timezone.utc).isoformat(),
                                team.get("region_pin"),
                                int(team.get("rpm") or 0),
                                int(team.get("tpm") or 0),
                            ),
                        )
                    for key in doc["keys"]:
                        windows = self._windows_json(
                            self._parse_windows(json.dumps(key.get("budget_windows") or []))
                        )
                        cur.execute(
                            "INSERT INTO virtual_keys (key_hash, key_id, name, prefix,"
                            " created_at, revoked_at, expires_at, daily_budget_usd,"
                            " monthly_budget_usd, rpm, tpm, tier_cap, client_id, team_id,"
                            " budget_windows_json, metadata_json, user_daily_usd_cap,"
                            " previous_key_hash, previous_prefix, previous_expires_at,"
                            " region_pin) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s,"
                            " %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
                            " ON CONFLICT (key_id) DO UPDATE SET"
                            " key_hash = EXCLUDED.key_hash,"
                            " name = EXCLUDED.name,"
                            " prefix = EXCLUDED.prefix,"
                            " revoked_at = EXCLUDED.revoked_at,"
                            " expires_at = EXCLUDED.expires_at,"
                            " daily_budget_usd = EXCLUDED.daily_budget_usd,"
                            " monthly_budget_usd = EXCLUDED.monthly_budget_usd,"
                            " rpm = EXCLUDED.rpm,"
                            " tpm = EXCLUDED.tpm,"
                            " tier_cap = EXCLUDED.tier_cap,"
                            " client_id = EXCLUDED.client_id,"
                            " team_id = EXCLUDED.team_id,"
                            " budget_windows_json = EXCLUDED.budget_windows_json,"
                            " metadata_json = EXCLUDED.metadata_json,"
                            " user_daily_usd_cap = EXCLUDED.user_daily_usd_cap,"
                            " previous_key_hash = EXCLUDED.previous_key_hash,"
                            " previous_prefix = EXCLUDED.previous_prefix,"
                            " previous_expires_at = EXCLUDED.previous_expires_at,"
                            " region_pin = EXCLUDED.region_pin",
                            (
                                key["key_hash"],
                                key["key_id"],
                                key["name"],
                                key["prefix"],
                                key.get("created_at") or datetime.now(timezone.utc).isoformat(),
                                key.get("revoked_at"),
                                key.get("expires_at"),
                                float(key.get("daily_budget_usd") or 0),
                                float(key.get("monthly_budget_usd") or 0),
                                int(key.get("rpm") or 0),
                                int(key.get("tpm") or 0),
                                key.get("tier_cap"),
                                key.get("client_id"),
                                key.get("team_id"),
                                windows,
                                json.dumps(key.get("metadata") or {}),
                                float(key.get("user_daily_usd_cap") or 0),
                                key.get("previous_key_hash"),
                                key.get("previous_prefix"),
                                key.get("previous_expires_at"),
                                key.get("region_pin"),
                            ),
                        )
                conn.commit()
            return summary
        finally:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass


def virtual_key_store_from_settings(settings: Any) -> VirtualKeyStore | PostgresVirtualKeyStore:
    """Construct SQLite or Postgres VirtualKeyStore from settings (#544)."""
    vk = getattr(getattr(settings, "server", None), "virtual_keys", None)
    enabled = bool(getattr(vk, "enabled", True))
    backend = getattr(vk, "backend", "sqlite") or "sqlite"
    pg_url = (getattr(getattr(settings, "observability", None), "postgres_url", "") or "").strip()
    if backend == "postgres" and pg_url:
        return PostgresVirtualKeyStore(pg_url, enabled=enabled)
    path = getattr(settings, "virtual_keys_path", None) or getattr(
        vk, "path", "~/.daari/auth/virtual-keys.sqlite3"
    )
    return VirtualKeyStore(path, enabled=enabled)
