"""Per-request spend rows for chargeback export (#709).

Opt-in. When `usage.spend.enabled` is false the store is never opened, so the
day-aggregated usage ledger stays byte-identical. SQLite is the default;
Postgres is used when `observability.backend` is postgres.
"""

from __future__ import annotations

import sqlite3
import threading
import uuid
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from daari.pricing import cost_usd

FRONTIER_TIER = "L6"

_COLUMNS = (
    "ts",
    "request_id",
    "key_id",
    "team_id",
    "client_id",
    "model",
    "tier",
    "input_tokens",
    "output_tokens",
    "cached_tokens",
    "cost_usd",
    "cost_avoided_usd",
    "cache_hit",
)

EXPORT_FIELDS = (
    "timestamp",
    "request_id",
    "key_id",
    "team_id",
    "client_id",
    "model",
    "tier",
    "input_tokens",
    "output_tokens",
    "cached_tokens",
    "cost_usd",
    "cost_avoided_usd",
    "cache_hit",
)

_SQLITE_SCHEMA = """
CREATE TABLE IF NOT EXISTS spend_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    request_id TEXT NOT NULL,
    key_id TEXT NOT NULL DEFAULT '',
    team_id TEXT NOT NULL DEFAULT '',
    client_id TEXT NOT NULL DEFAULT '',
    model TEXT NOT NULL DEFAULT '',
    tier TEXT NOT NULL DEFAULT '',
    input_tokens INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    cached_tokens INTEGER NOT NULL DEFAULT 0,
    cost_usd REAL NOT NULL DEFAULT 0,
    cost_avoided_usd REAL NOT NULL DEFAULT 0,
    cache_hit INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_spend_requests_ts ON spend_requests (ts);
CREATE INDEX IF NOT EXISTS idx_spend_requests_key ON spend_requests (key_id);
CREATE INDEX IF NOT EXISTS idx_spend_requests_team ON spend_requests (team_id);
"""

_POSTGRES_SCHEMA = """
CREATE TABLE IF NOT EXISTS spend_requests (
    id BIGSERIAL PRIMARY KEY,
    ts TEXT NOT NULL,
    request_id TEXT NOT NULL,
    key_id TEXT NOT NULL DEFAULT '',
    team_id TEXT NOT NULL DEFAULT '',
    client_id TEXT NOT NULL DEFAULT '',
    model TEXT NOT NULL DEFAULT '',
    tier TEXT NOT NULL DEFAULT '',
    input_tokens INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    cached_tokens INTEGER NOT NULL DEFAULT 0,
    cost_usd DOUBLE PRECISION NOT NULL DEFAULT 0,
    cost_avoided_usd DOUBLE PRECISION NOT NULL DEFAULT 0,
    cache_hit INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_spend_requests_ts ON spend_requests (ts);
CREATE INDEX IF NOT EXISTS idx_spend_requests_key ON spend_requests (key_id);
CREATE INDEX IF NOT EXISTS idx_spend_requests_team ON spend_requests (team_id);
"""


@dataclass
class SpendContext:
    key_id: str = ""
    team_id: str = ""
    client_id: str = ""
    request_id: str = ""
    requested_model: str = ""
    service_tier: str | None = None
    pricing: Any = None
    fallback_per_1k: float = 0.002
    reported_cost: float | None = None
    cached_tokens: int = 0


_spend_ctx: ContextVar[SpendContext | None] = ContextVar("daari_spend_ctx", default=None)


def bind_spend_context(ctx: SpendContext) -> Any:
    return _spend_ctx.set(ctx)


def current_spend_context() -> SpendContext | None:
    return _spend_ctx.get()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def compute_request_usd(
    *,
    tier: str,
    model: str | None,
    input_tokens: int,
    output_tokens: int,
    cached_tokens: int,
    pricing: object,
    fallback_per_1k: float,
    reported_cost: float | None = None,
    service_tier: str | None = None,
    avoided_model: str | None = None,
) -> tuple[float, float]:
    """Return (cost_usd, cost_avoided_usd). Local tiers cost $0."""
    if (tier or "").upper() == FRONTIER_TIER:
        if reported_cost is not None:
            spent = float(reported_cost)
        else:
            spent = cost_usd(
                model,
                int(input_tokens),
                int(output_tokens),
                pricing,
                fallback_per_1k=fallback_per_1k,
                cached_input_tokens=int(cached_tokens),
                service_tier=service_tier,
            )
        return round(max(0.0, spent), 8), 0.0
    avoided = cost_usd(
        avoided_model or model,
        int(input_tokens),
        int(output_tokens),
        pricing,
        fallback_per_1k=fallback_per_1k,
        cached_input_tokens=int(cached_tokens),
        service_tier=service_tier,
    )
    return 0.0, round(max(0.0, avoided), 8)


def export_dict(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "timestamp": row["ts"],
        "request_id": row["request_id"],
        "key_id": row["key_id"],
        "team_id": row["team_id"],
        "client_id": row["client_id"],
        "model": row["model"],
        "tier": row["tier"],
        "input_tokens": int(row["input_tokens"]),
        "output_tokens": int(row["output_tokens"]),
        "cached_tokens": int(row["cached_tokens"]),
        "cost_usd": float(row["cost_usd"]),
        "cost_avoided_usd": float(row["cost_avoided_usd"]),
        "cache_hit": bool(row["cache_hit"]),
    }


def _where(since: str, key_id: str | None, team_id: str | None, ph: str) -> tuple[str, list[Any]]:
    clauses = [f"ts >= {ph}"]
    params: list[Any] = [since]
    if key_id:
        clauses.append(f"key_id = {ph}")
        params.append(key_id)
    if team_id:
        clauses.append(f"team_id = {ph}")
        params.append(team_id)
    return " AND ".join(clauses), params


def _tuple_to_row(values: tuple[Any, ...]) -> dict[str, Any]:
    row = dict(zip(_COLUMNS, values, strict=True))
    row["cache_hit"] = bool(row["cache_hit"])
    return row


class SpendLedger:
    def __init__(self, path: str | Path, enabled: bool = True) -> None:
        self.path = Path(path).expanduser()
        self.enabled = enabled
        self._lock = threading.Lock()
        if not self.enabled:
            return
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self._connect() as conn:
                conn.executescript(_SQLITE_SCHEMA)
        except Exception:
            self.enabled = False

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path, timeout=5.0)

    def record(
        self,
        *,
        ts: str | None = None,
        request_id: str = "",
        key_id: str = "",
        team_id: str = "",
        client_id: str = "",
        model: str = "",
        tier: str = "",
        input_tokens: int = 0,
        output_tokens: int = 0,
        cached_tokens: int = 0,
        cost_usd: float = 0.0,
        cost_avoided_usd: float = 0.0,
        cache_hit: bool = False,
    ) -> None:
        if not self.enabled:
            return
        try:
            with self._lock, self._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO spend_requests (
                        ts, request_id, key_id, team_id, client_id, model, tier,
                        input_tokens, output_tokens, cached_tokens,
                        cost_usd, cost_avoided_usd, cache_hit
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        ts or _now_iso(),
                        request_id or uuid.uuid4().hex[:16],
                        key_id or "",
                        team_id or "",
                        client_id or "",
                        model or "",
                        tier or "",
                        max(0, int(input_tokens)),
                        max(0, int(output_tokens)),
                        max(0, int(cached_tokens)),
                        float(cost_usd),
                        float(cost_avoided_usd),
                        1 if cache_hit else 0,
                    ),
                )
        except Exception:
            pass

    def record_from_usage(self, ctx: SpendContext | None = None, **kwargs: Any) -> None:
        if not self.enabled:
            return
        bound = ctx if ctx is not None else current_spend_context()
        bound = bound or SpendContext()
        served = kwargs.get("model") or bound.requested_model or ""
        price_model = bound.requested_model or served
        tokens_in = int(kwargs.get("input_tokens") or 0)
        tokens_out = int(kwargs.get("output_tokens") or 0)
        cached = kwargs.get("cached_tokens")
        if cached is None:
            cached = bound.cached_tokens
        reported = kwargs.get("reported_cost")
        if reported is None:
            reported = bound.reported_cost
        cost, avoided = compute_request_usd(
            tier=str(kwargs.get("tier") or ""),
            model=served,
            avoided_model=price_model,
            input_tokens=tokens_in,
            output_tokens=tokens_out,
            cached_tokens=int(cached or 0),
            pricing=bound.pricing,
            fallback_per_1k=float(bound.fallback_per_1k or 0.002),
            reported_cost=reported,
            service_tier=bound.service_tier,
        )
        client = kwargs.get("client_id") or bound.client_id or ""
        self.record(
            ts=kwargs.get("ts"),
            request_id=bound.request_id or str(kwargs.get("request_id") or ""),
            key_id=bound.key_id or str(kwargs.get("key_id") or ""),
            team_id=bound.team_id or str(kwargs.get("team_id") or ""),
            client_id=str(client),
            model=str(served),
            tier=str(kwargs.get("tier") or ""),
            input_tokens=tokens_in,
            output_tokens=tokens_out,
            cached_tokens=int(cached or 0),
            cost_usd=cost,
            cost_avoided_usd=avoided,
            cache_hit=bool(kwargs.get("cache_hit")),
        )

    def iter_rows(
        self,
        *,
        since: str,
        key_id: str | None = None,
        team_id: str | None = None,
    ) -> Iterator[dict[str, Any]]:
        if not self.enabled:
            return
        where, params = _where(since, key_id, team_id, "?")
        sql = (
            "SELECT ts, request_id, key_id, team_id, client_id, model, tier,"
            " input_tokens, output_tokens, cached_tokens, cost_usd, cost_avoided_usd, cache_hit"
            f" FROM spend_requests WHERE {where} ORDER BY ts, id"
        )
        try:
            with self._lock, self._connect() as conn:
                cursor = conn.execute(sql, params)
                while True:
                    batch = cursor.fetchmany(200)
                    if not batch:
                        break
                    for values in batch:
                        yield _tuple_to_row(values)
        except Exception:
            return

    def prune_before(self, cutoff_iso: str, *, dry_run: bool = False) -> int:
        if not self.enabled:
            return 0
        try:
            with self._lock, self._connect() as conn:
                count = conn.execute(
                    "SELECT COUNT(*) FROM spend_requests WHERE ts < ?",
                    (cutoff_iso,),
                ).fetchone()[0]
                if not dry_run and count:
                    conn.execute("DELETE FROM spend_requests WHERE ts < ?", (cutoff_iso,))
                return int(count)
        except Exception:
            return 0


class PostgresSpendLedger(SpendLedger):
    """Duck-types SpendLedger against observability.postgres_url."""

    def __init__(self, dsn: str, enabled: bool = True) -> None:
        self.dsn = dsn
        self.path = dsn
        self.enabled = enabled
        self._lock = threading.Lock()
        if not self.enabled:
            return
        try:
            with self._connect() as conn:
                with conn.cursor() as cur:
                    for statement in _POSTGRES_SCHEMA.split(";"):
                        sql = statement.strip()
                        if sql:
                            cur.execute(sql)
                conn.commit()
        except Exception:
            self.enabled = False

    def _connect(self) -> Any:
        try:
            import psycopg
        except ImportError as exc:
            raise RuntimeError(
                "observability.backend=postgres requires psycopg — "
                "pip install 'psycopg[binary]>=3' (or daari[postgres])"
            ) from exc
        return psycopg.connect(self.dsn)

    def record(
        self,
        *,
        ts: str | None = None,
        request_id: str = "",
        key_id: str = "",
        team_id: str = "",
        client_id: str = "",
        model: str = "",
        tier: str = "",
        input_tokens: int = 0,
        output_tokens: int = 0,
        cached_tokens: int = 0,
        cost_usd: float = 0.0,
        cost_avoided_usd: float = 0.0,
        cache_hit: bool = False,
    ) -> None:
        if not self.enabled:
            return
        try:
            with self._lock, self._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO spend_requests (
                            ts, request_id, key_id, team_id, client_id, model, tier,
                            input_tokens, output_tokens, cached_tokens,
                            cost_usd, cost_avoided_usd, cache_hit
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """,
                        (
                            ts or _now_iso(),
                            request_id or uuid.uuid4().hex[:16],
                            key_id or "",
                            team_id or "",
                            client_id or "",
                            model or "",
                            tier or "",
                            max(0, int(input_tokens)),
                            max(0, int(output_tokens)),
                            max(0, int(cached_tokens)),
                            float(cost_usd),
                            float(cost_avoided_usd),
                            1 if cache_hit else 0,
                        ),
                    )
                conn.commit()
        except Exception:
            pass

    def iter_rows(
        self,
        *,
        since: str,
        key_id: str | None = None,
        team_id: str | None = None,
    ) -> Iterator[dict[str, Any]]:
        if not self.enabled:
            return
        where, params = _where(since, key_id, team_id, "%s")
        sql = (
            "SELECT ts, request_id, key_id, team_id, client_id, model, tier,"
            " input_tokens, output_tokens, cached_tokens, cost_usd, cost_avoided_usd, cache_hit"
            f" FROM spend_requests WHERE {where} ORDER BY ts, id"
        )
        try:
            with self._lock, self._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(sql, params)
                    while True:
                        batch = cur.fetchmany(200)
                        if not batch:
                            break
                        for values in batch:
                            yield _tuple_to_row(values)
        except Exception:
            return

    def prune_before(self, cutoff_iso: str, *, dry_run: bool = False) -> int:
        if not self.enabled:
            return 0
        try:
            with self._lock, self._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT COUNT(*) FROM spend_requests WHERE ts < %s",
                        (cutoff_iso,),
                    )
                    count = int(cur.fetchone()[0])
                    if not dry_run and count:
                        cur.execute(
                            "DELETE FROM spend_requests WHERE ts < %s",
                            (cutoff_iso,),
                        )
                conn.commit()
                return count
        except Exception:
            return 0


def install_spend_hook(usage_ledger: Any, spend_ledger: Any) -> None:
    """Attach a best-effort callback. No-op when the spend log is off."""
    if usage_ledger is None or spend_ledger is None or not getattr(spend_ledger, "enabled", False):
        return

    def _hook(**kwargs: Any) -> None:
        try:
            spend_ledger.record_from_usage(current_spend_context(), **kwargs)
        except Exception:
            pass

    usage_ledger.on_recorded = _hook


def spend_ledger_from_settings(settings: Any) -> SpendLedger:
    spend = settings.usage.spend
    enabled = bool(getattr(spend, "enabled", False))
    backend = getattr(settings.observability, "backend", "sqlite")
    url = (getattr(settings.observability, "postgres_url", "") or "").strip()
    if backend == "postgres" and url:
        return PostgresSpendLedger(url, enabled=enabled)
    return SpendLedger(Path(spend.path).expanduser(), enabled=enabled)
