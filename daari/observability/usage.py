"""Persistent per-day usage ledger with frontier-savings estimation.

Metrics (daari/observability/metrics.py) are in-memory and reset on restart;
this ledger survives restarts so `daari report` can show accumulated local
usage and the frontier spend it avoided. Recording is best-effort: failures
must never propagate into the request path.
"""

from __future__ import annotations

import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from daari.pricing import cost_usd

FRONTIER_TIER = "L6"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS usage (
    day TEXT NOT NULL,
    tier TEXT NOT NULL,
    model TEXT NOT NULL DEFAULT '',
    provider TEXT NOT NULL DEFAULT '',
    requests INTEGER NOT NULL DEFAULT 0,
    cache_hits INTEGER NOT NULL DEFAULT 0,
    prompt_chars INTEGER NOT NULL DEFAULT 0,
    completion_chars INTEGER NOT NULL DEFAULT 0,
    input_tokens INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (day, tier, model)
);
CREATE TABLE IF NOT EXISTS client_usage (
    day TEXT NOT NULL,
    client_id TEXT NOT NULL,
    tier TEXT NOT NULL,
    model TEXT NOT NULL DEFAULT '',
    requests INTEGER NOT NULL DEFAULT 0,
    cache_hits INTEGER NOT NULL DEFAULT 0,
    prompt_chars INTEGER NOT NULL DEFAULT 0,
    completion_chars INTEGER NOT NULL DEFAULT 0,
    input_tokens INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (day, client_id, tier, model)
);
"""

# Ledgers created before #156 lack the token and model columns, and their
# primary key omits `model`. ALTER TABLE ADD COLUMN cannot change a primary key,
# and the upsert needs (day, tier, model) as its conflict target, so migration
# rebuilds the table and copies the old rows across.
_MIGRATED_TABLES = ("usage", "client_usage")


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _empty_totals() -> dict[str, Any]:
    return {
        "requests": 0,
        "cache_hits": 0,
        "local_requests": 0,
        "frontier_requests": 0,
        "estimated_saved_usd": 0.0,
    }


class UsageLedger:
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
    def _migrate(conn: sqlite3.Connection) -> None:
        for table in _MIGRATED_TABLES:
            columns = [row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()]
            if not columns or "model" in columns:
                continue
            carried = [name for name in columns if name != "model"]
            conn.execute(f"ALTER TABLE {table} RENAME TO {table}_pre_tokens")
            conn.executescript(_SCHEMA)
            conn.execute(
                f"INSERT INTO {table} ({', '.join(carried)}) "
                f"SELECT {', '.join(carried)} FROM {table}_pre_tokens"
            )
            conn.execute(f"DROP TABLE {table}_pre_tokens")

    def record(
        self,
        *,
        tier: str,
        cache_hit: bool = False,
        prompt_chars: int = 0,
        completion_chars: int = 0,
        day: str | None = None,
        client_id: str | None = None,
        model: str | None = None,
        provider: str | None = None,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
    ) -> None:
        if not self.enabled:
            return
        # Fall back to the chars/4 estimate only when the provider reported
        # nothing, so old call sites keep working (#156).
        tokens_in = max(0, input_tokens if input_tokens is not None else prompt_chars // 4)
        tokens_out = max(
            0, output_tokens if output_tokens is not None else completion_chars // 4
        )
        try:
            with self._lock, self._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO usage (day, tier, model, provider, requests, cache_hits,
                                       prompt_chars, completion_chars, input_tokens, output_tokens)
                    VALUES (?, ?, ?, ?, 1, ?, ?, ?, ?, ?)
                    ON CONFLICT(day, tier, model) DO UPDATE SET
                        requests = requests + 1,
                        cache_hits = cache_hits + excluded.cache_hits,
                        prompt_chars = prompt_chars + excluded.prompt_chars,
                        completion_chars = completion_chars + excluded.completion_chars,
                        input_tokens = input_tokens + excluded.input_tokens,
                        output_tokens = output_tokens + excluded.output_tokens,
                        provider = excluded.provider
                    """,
                    (
                        day or _today(),
                        tier,
                        model or "",
                        provider or "",
                        1 if cache_hit else 0,
                        max(0, prompt_chars),
                        max(0, completion_chars),
                        tokens_in,
                        tokens_out,
                    ),
                )
                conn.execute(
                    """
                    INSERT INTO client_usage (day, client_id, tier, model, requests, cache_hits,
                                              prompt_chars, completion_chars, input_tokens, output_tokens)
                    VALUES (?, ?, ?, ?, 1, ?, ?, ?, ?, ?)
                    ON CONFLICT(day, client_id, tier, model) DO UPDATE SET
                        requests = requests + 1,
                        cache_hits = cache_hits + excluded.cache_hits,
                        prompt_chars = prompt_chars + excluded.prompt_chars,
                        completion_chars = completion_chars + excluded.completion_chars,
                        input_tokens = input_tokens + excluded.input_tokens,
                        output_tokens = output_tokens + excluded.output_tokens
                    """,
                    (
                        day or _today(),
                        client_id or "unknown",
                        tier,
                        model or "",
                        1 if cache_hit else 0,
                        max(0, prompt_chars),
                        max(0, completion_chars),
                        tokens_in,
                        tokens_out,
                    ),
                )
        except Exception:
            pass

    def by_client(
        self, days: int = 7, *, frontier_price_per_1k_tokens: float = 0.002
    ) -> list[dict[str, Any]]:
        """Per-client usage and savings attribution (Trust PRD T5b)."""
        if not self.enabled:
            return []
        cutoff = (datetime.now(timezone.utc) - timedelta(days=max(0, days - 1))).strftime(
            "%Y-%m-%d"
        )
        try:
            with self._lock, self._connect() as conn:
                rows = conn.execute(
                    "SELECT client_id, tier, SUM(requests), SUM(cache_hits),"
                    " SUM(prompt_chars), SUM(completion_chars)"
                    " FROM client_usage WHERE day >= ? GROUP BY client_id, tier",
                    (cutoff,),
                ).fetchall()
        except Exception:
            return []
        clients: dict[str, dict[str, Any]] = {}
        for client_id, tier, requests, cache_hits, prompt_chars, completion_chars in rows:
            entry = clients.setdefault(
                client_id,
                {
                    "client_id": client_id,
                    "requests": 0,
                    "cache_hits": 0,
                    "local_requests": 0,
                    "frontier_requests": 0,
                    "estimated_saved_usd": 0.0,
                },
            )
            entry["requests"] += requests
            entry["cache_hits"] += cache_hits
            if tier == FRONTIER_TIER:
                entry["frontier_requests"] += requests
            else:
                entry["local_requests"] += requests
                tokens = (prompt_chars + completion_chars) / 4
                entry["estimated_saved_usd"] += tokens / 1000 * frontier_price_per_1k_tokens
        for entry in clients.values():
            entry["estimated_saved_usd"] = round(entry["estimated_saved_usd"], 4)
        return sorted(clients.values(), key=lambda entry: -entry["requests"])

    def _spend_for(
        self,
        where: str,
        params: tuple[Any, ...],
        *,
        pricing: Any,
        fallback_per_1k: float,
        table: str = "usage",
    ) -> float:
        """Sum L6 spend, pricing each model at its own rate (#157).

        `table` selects the global ledger or the per-client one; both carry the
        model and token columns, so pricing works identically for either.
        """
        if table not in _MIGRATED_TABLES:
            raise ValueError(f"unknown usage table: {table}")
        try:
            with self._lock, self._connect() as conn:
                rows = conn.execute(
                    "SELECT model, COALESCE(SUM(input_tokens), 0), COALESCE(SUM(output_tokens), 0)"
                    f" FROM {table} WHERE {where} AND tier = ? GROUP BY model",
                    (*params, FRONTIER_TIER),
                ).fetchall()
        except Exception:
            return 0.0
        total = 0.0
        for model, input_tokens, output_tokens in rows:
            total += cost_usd(
                model or None,
                input_tokens,
                output_tokens,
                pricing,
                fallback_per_1k=fallback_per_1k,
            )
        return total

    def frontier_spend_usd(
        self,
        *,
        pricing: Any = None,
        fallback_per_1k: float = 0.002,
        price_per_1k_tokens: float | None = None,
        day: str | None = None,
    ) -> float:
        """USD spent on the frontier tier for the given UTC day."""
        if not self.enabled:
            return 0.0
        if price_per_1k_tokens is not None:
            fallback_per_1k = price_per_1k_tokens
        return self._spend_for(
            "day = ?",
            (day or _today(),),
            pricing=pricing,
            fallback_per_1k=fallback_per_1k,
        )

    def frontier_spend_usd_month(
        self,
        *,
        pricing: Any = None,
        fallback_per_1k: float = 0.002,
        price_per_1k_tokens: float | None = None,
        month: str | None = None,
    ) -> float:
        """USD spent on L6 for the given UTC month (Trust PRD T5a)."""
        if not self.enabled:
            return 0.0
        if price_per_1k_tokens is not None:
            fallback_per_1k = price_per_1k_tokens
        return self._spend_for(
            "day LIKE ?",
            ((month or _today()[:7]) + "-%",),
            pricing=pricing,
            fallback_per_1k=fallback_per_1k,
        )

    def frontier_spend_usd_for_client(
        self,
        client_id: str,
        *,
        window: str = "day",
        pricing: Any = None,
        fallback_per_1k: float = 0.002,
        day: str | None = None,
        month: str | None = None,
    ) -> float:
        """USD one client spent on the frontier tier (#158).

        Virtual-key budgets must be charged to the key that caused the spend;
        billing them against global spend lets one key exhaust every other key.
        `window` is `day` or `month`.
        """
        if not self.enabled or not client_id:
            return 0.0
        if window == "month":
            where, params = "client_id = ? AND day LIKE ?", (
                client_id,
                (month or _today()[:7]) + "-%",
            )
        elif window == "day":
            where, params = "client_id = ? AND day = ?", (client_id, day or _today())
        else:
            raise ValueError(f"window must be 'day' or 'month', got {window!r}")
        return self._spend_for(
            where,
            params,
            pricing=pricing,
            fallback_per_1k=fallback_per_1k,
            table="client_usage",
        )

    def frontier_spend_usd_for_client_days(
        self,
        client_id: str,
        *,
        days: int,
        pricing: Any = None,
        fallback_per_1k: float = 0.002,
    ) -> float:
        """USD one client spent on L6 across the last `days` UTC calendar days."""
        if not self.enabled or not client_id or days <= 0:
            return 0.0
        cutoff = (datetime.now(timezone.utc) - timedelta(days=max(0, days - 1))).strftime(
            "%Y-%m-%d"
        )
        return self._spend_for(
            "client_id = ? AND day >= ?",
            (client_id, cutoff),
            pricing=pricing,
            fallback_per_1k=fallback_per_1k,
            table="client_usage",
        )

    def report(self, days: int = 7, *, frontier_price_per_1k_tokens: float = 0.002) -> dict[str, Any]:
        if not self.enabled:
            return {"enabled": False, "days": [], "totals": _empty_totals()}
        cutoff = (datetime.now(timezone.utc) - timedelta(days=max(0, days - 1))).strftime("%Y-%m-%d")
        try:
            with self._lock, self._connect() as conn:
                rows = conn.execute(
                    "SELECT day, tier, requests, cache_hits, prompt_chars, completion_chars"
                    " FROM usage WHERE day >= ? ORDER BY day",
                    (cutoff,),
                ).fetchall()
        except Exception:
            return {"enabled": False, "days": [], "totals": _empty_totals()}

        per_day: dict[str, dict[str, Any]] = {}
        totals = _empty_totals()
        for day, tier, requests, cache_hits, prompt_chars, completion_chars in rows:
            entry = per_day.setdefault(
                day,
                {
                    "day": day,
                    "requests": 0,
                    "cache_hits": 0,
                    "prompt_chars": 0,
                    "completion_chars": 0,
                    "tiers": {},
                },
            )
            entry["requests"] += requests
            entry["cache_hits"] += cache_hits
            entry["prompt_chars"] += prompt_chars
            entry["completion_chars"] += completion_chars
            # One tier can now have several rows, one per model, so accumulate
            # rather than assign (#156).
            tier_entry = entry["tiers"].setdefault(
                tier,
                {"requests": 0, "cache_hits": 0, "prompt_chars": 0, "completion_chars": 0},
            )
            tier_entry["requests"] += requests
            tier_entry["cache_hits"] += cache_hits
            tier_entry["prompt_chars"] += prompt_chars
            tier_entry["completion_chars"] += completion_chars
            totals["requests"] += requests
            totals["cache_hits"] += cache_hits
            if tier == FRONTIER_TIER:
                totals["frontier_requests"] += requests
            else:
                totals["local_requests"] += requests
                # chars/4 ~ tokens, priced as if a frontier model had served them.
                tokens = (prompt_chars + completion_chars) / 4
                totals["estimated_saved_usd"] += tokens / 1000 * frontier_price_per_1k_tokens
        totals["estimated_saved_usd"] = round(totals["estimated_saved_usd"], 4)
        return {"enabled": True, "days": list(per_day.values()), "totals": totals}
