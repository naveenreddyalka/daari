"""Per-end-user governance on shared virtual keys (#1547).

End-users (OpenAI ``user`` / Anthropic ``metadata.user_id``) are ledger
dimensions. This module adds the registry on top: an admin ``blocked`` flag
and a per-user daily USD cap that override the key-level
``user_daily_usd_cap``. Rows live next to virtual keys so both SQLite and
Postgres stores carry them without new infrastructure.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

END_USER_BLOCKED_TYPE = "end_user_blocked"

END_USER_OVERRIDES_SQLITE_SCHEMA = """
CREATE TABLE IF NOT EXISTS end_user_overrides (
    user_id TEXT PRIMARY KEY,
    blocked INTEGER NOT NULL DEFAULT 0,
    user_usd_cap REAL NOT NULL DEFAULT 0,
    reason TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""

END_USER_OVERRIDES_PG_SCHEMA = """
CREATE TABLE IF NOT EXISTS end_user_overrides (
    user_id TEXT PRIMARY KEY,
    blocked BOOLEAN NOT NULL DEFAULT FALSE,
    user_usd_cap DOUBLE PRECISION NOT NULL DEFAULT 0,
    reason TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""


@dataclass(frozen=True)
class EndUserOverride:
    user_id: str
    blocked: bool = False
    # Daily USD cap across every key this user presents on (0 = inherit key cap).
    user_usd_cap: float = 0.0
    reason: str | None = None
    created_at: str = ""
    updated_at: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "user_id": self.user_id,
            "blocked": bool(self.blocked),
            "user_usd_cap": float(self.user_usd_cap or 0.0),
            "reason": self.reason,
            "created_at": self.created_at or None,
            "updated_at": self.updated_at or None,
        }


def normalize_end_user_id(user_id: Any) -> str:
    named = str(user_id or "").strip()
    if not named:
        raise ValueError("user_id is required")
    if len(named) > 256:
        raise ValueError("user_id must be at most 256 characters")
    return named


def coerce_user_usd_cap(value: Any) -> float:
    try:
        cap = float(value if value is not None else 0.0)
    except (TypeError, ValueError) as exc:
        raise ValueError("user_usd_cap must be a non-negative number") from exc
    if cap != cap or cap < 0:
        raise ValueError("user_usd_cap must be a non-negative number")
    return cap


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def override_from_row(row: Any) -> EndUserOverride:
    user_id, blocked, cap, reason, created_at, updated_at = row
    return EndUserOverride(
        user_id=str(user_id),
        blocked=bool(blocked),
        user_usd_cap=float(cap or 0.0),
        reason=str(reason) if reason else None,
        created_at=str(created_at or ""),
        updated_at=str(updated_at or ""),
    )


class SqliteEndUserOverrides:
    """``end_user_overrides`` CRUD on a VirtualKeyStore-owned SQLite connection."""

    def __init__(self, connect: Any, lock: Any) -> None:
        self._connect = connect
        self._lock = lock

    _SELECT = (
        "SELECT user_id, blocked, user_usd_cap, reason, created_at, updated_at"
        " FROM end_user_overrides"
    )

    def get(self, user_id: str) -> EndUserOverride | None:
        named = str(user_id or "").strip()
        if not named:
            return None
        with self._lock, self._connect() as conn:
            row = conn.execute(f"{self._SELECT} WHERE user_id = ?", (named,)).fetchone()
        return override_from_row(row) if row else None

    def list(self) -> list[EndUserOverride]:
        with self._lock, self._connect() as conn:
            rows = conn.execute(f"{self._SELECT} ORDER BY user_id").fetchall()
        return [override_from_row(row) for row in rows]

    def _upsert(
        self,
        user_id: str,
        *,
        blocked: bool | None = None,
        user_usd_cap: float | None = None,
        reason: str | None = None,
        clear_reason: bool = False,
    ) -> EndUserOverride:
        named = normalize_end_user_id(user_id)
        now = _now()
        with self._lock, self._connect() as conn:
            current = conn.execute(f"{self._SELECT} WHERE user_id = ?", (named,)).fetchone()
            existing = override_from_row(current) if current else None
            next_blocked = existing.blocked if existing else False
            next_cap = existing.user_usd_cap if existing else 0.0
            next_reason = existing.reason if existing else None
            if blocked is not None:
                next_blocked = bool(blocked)
            if user_usd_cap is not None:
                next_cap = float(user_usd_cap)
            if clear_reason:
                next_reason = None
            if reason is not None:
                next_reason = str(reason).strip() or None
            created = existing.created_at if existing else now
            conn.execute(
                "INSERT INTO end_user_overrides"
                " (user_id, blocked, user_usd_cap, reason, created_at, updated_at)"
                " VALUES (?, ?, ?, ?, ?, ?)"
                " ON CONFLICT(user_id) DO UPDATE SET"
                " blocked = excluded.blocked, user_usd_cap = excluded.user_usd_cap,"
                " reason = excluded.reason, updated_at = excluded.updated_at",
                (named, 1 if next_blocked else 0, next_cap, next_reason, created, now),
            )
        return EndUserOverride(
            user_id=named,
            blocked=next_blocked,
            user_usd_cap=next_cap,
            reason=next_reason,
            created_at=created,
            updated_at=now,
        )

    def set_blocked(
        self, user_id: str, blocked: bool, *, reason: str | None = None
    ) -> EndUserOverride:
        # Unblocking clears the stored reason; blocking records the new one.
        return self._upsert(
            user_id,
            blocked=bool(blocked),
            reason=reason if blocked else None,
            clear_reason=not blocked,
        )

    def set_cap(self, user_id: str, daily_usd: Any) -> EndUserOverride:
        return self._upsert(user_id, user_usd_cap=coerce_user_usd_cap(daily_usd))

    def delete(self, user_id: str) -> bool:
        named = str(user_id or "").strip()
        if not named:
            return False
        with self._lock, self._connect() as conn:
            cur = conn.execute("DELETE FROM end_user_overrides WHERE user_id = ?", (named,))
            return cur.rowcount > 0


def end_user_blocked_error(user_id: str, *, reason: str | None = None) -> dict[str, Any]:
    """403 body for an admin-blocked end-user (#1547)."""
    payload: dict[str, Any] = {
        "type": END_USER_BLOCKED_TYPE,
        "code": END_USER_BLOCKED_TYPE,
        "message": (
            f"End user {user_id!r} is blocked by the daari administrator. "
            "Contact your administrator to restore access."
        ),
        "user_id": user_id,
    }
    if reason:
        payload["reason"] = reason
    return payload


def end_user_denial(
    store: Any,
    ledger: Any,
    *,
    key: Any,
    client_id: str,
    user_id: str | None,
    pricing: Any = None,
    fallback_per_1k: float = 0.002,
) -> tuple[int, dict[str, Any]] | None:
    """(status, error body) when ``user_id`` must be refused, else None.

    Order: admin block (403) → per-user cap override across keys (402) →
    key-level ``user_daily_usd_cap`` / lifetime cap (402). A per-user cap
    override replaces the key's daily cap but leaves the key lifetime cap
    (``metadata.user_lifetime_usd_cap``) in force. Missing store/ledger fails open,
    matching the key-level pre-check.
    """
    named = (user_id or "").strip()
    if not named:
        return None
    override: EndUserOverride | None = None
    getter = getattr(store, "get_end_user", None) if store is not None else None
    if callable(getter) and getattr(store, "enabled", True):
        try:
            override = getter(named)
        except Exception:
            override = None
    if override is not None and override.blocked:
        return 403, end_user_blocked_error(named, reason=override.reason)

    override_cap = float(override.user_usd_cap or 0.0) if override is not None else 0.0
    if override_cap > 0:
        if ledger is None or not getattr(ledger, "enabled", False):
            return None
        spend_fn = getattr(ledger, "frontier_spend_usd_for_end_user", None)
        spend = 0.0
        if callable(spend_fn):
            try:
                spend = float(
                    spend_fn(
                        named,
                        window="day",
                        pricing=pricing,
                        fallback_per_1k=fallback_per_1k,
                    )
                    or 0.0
                )
            except Exception:
                spend = 0.0
        if spend >= override_cap:
            from daari.auth.budgets import user_cap_error

            return 402, user_cap_error(
                client_id=client_id,
                user_id=named,
                spend=spend,
                cap_usd=override_cap,
            )

    if key is None or ledger is None:
        return None
    subject = key
    if override_cap > 0 and float(getattr(key, "user_daily_usd_cap", 0) or 0) > 0:
        subject = dataclasses.replace(key, user_daily_usd_cap=0.0)
    if (
        float(getattr(subject, "user_daily_usd_cap", 0) or 0) <= 0
        and float((getattr(subject, "metadata", None) or {}).get("user_lifetime_usd_cap") or 0)
        <= 0
    ):
        return None
    from daari.auth.budgets import user_daily_cap_exceeded

    exceeded = user_daily_cap_exceeded(
        subject,
        ledger,
        client_id=client_id,
        user_id=named,
        pricing=pricing,
        fallback_per_1k=fallback_per_1k,
    )
    if exceeded is not None:
        return 402, exceeded
    return None
