"""Postgres-backed usage ledger for stateless gateway replicas (issue #116).

Duck-types UsageLedger. Requires optional `psycopg[binary]` (daari[postgres]).
"""

from __future__ import annotations

import threading
from datetime import datetime, timedelta, timezone
from typing import Any

from daari.observability.usage import FRONTIER_TIER, _empty_totals

_SCHEMA = """
CREATE TABLE IF NOT EXISTS usage (
    day TEXT NOT NULL,
    tier TEXT NOT NULL,
    requests INTEGER NOT NULL DEFAULT 0,
    cache_hits INTEGER NOT NULL DEFAULT 0,
    prompt_chars INTEGER NOT NULL DEFAULT 0,
    completion_chars INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (day, tier)
);
CREATE TABLE IF NOT EXISTS client_usage (
    day TEXT NOT NULL,
    client_id TEXT NOT NULL,
    tier TEXT NOT NULL,
    requests INTEGER NOT NULL DEFAULT 0,
    cache_hits INTEGER NOT NULL DEFAULT 0,
    prompt_chars INTEGER NOT NULL DEFAULT 0,
    completion_chars INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (day, client_id, tier)
);
CREATE TABLE IF NOT EXISTS user_usage (
    day TEXT NOT NULL,
    client_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    tier TEXT NOT NULL,
    requests INTEGER NOT NULL DEFAULT 0,
    cache_hits INTEGER NOT NULL DEFAULT 0,
    prompt_chars INTEGER NOT NULL DEFAULT 0,
    completion_chars INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (day, client_id, user_id, tier)
);
CREATE TABLE IF NOT EXISTS budget_window_state (
    scope TEXT NOT NULL,
    scope_id TEXT NOT NULL,
    duration TEXT NOT NULL,
    period_id TEXT NOT NULL,
    carry_usd DOUBLE PRECISION NOT NULL DEFAULT 0,
    PRIMARY KEY (scope, scope_id, duration)
);
"""


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


class PostgresUsageLedger:
    def __init__(self, dsn: str, enabled: bool = True) -> None:
        self.dsn = dsn
        self.enabled = enabled
        self.path = dsn  # Compatibility with code that logs ledger.path
        self._lock = threading.Lock()
        if self.enabled:
            try:
                with self._connect() as conn:
                    with conn.cursor() as cur:
                        cur.execute(_SCHEMA)
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
        tier: str,
        cache_hit: bool = False,
        prompt_chars: int = 0,
        completion_chars: int = 0,
        day: str | None = None,
        client_id: str | None = None,
        user_id: str | None = None,
        model: str | None = None,
        provider: str | None = None,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
    ) -> None:
        if not self.enabled:
            return
        del model, provider, input_tokens, output_tokens  # SQLite ledger owns token pricing
        try:
            with self._lock, self._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO usage (day, tier, requests, cache_hits, prompt_chars, completion_chars)
                        VALUES (%s, %s, 1, %s, %s, %s)
                        ON CONFLICT (day, tier) DO UPDATE SET
                            requests = usage.requests + 1,
                            cache_hits = usage.cache_hits + EXCLUDED.cache_hits,
                            prompt_chars = usage.prompt_chars + EXCLUDED.prompt_chars,
                            completion_chars = usage.completion_chars + EXCLUDED.completion_chars
                        """,
                        (
                            day or _today(),
                            tier,
                            1 if cache_hit else 0,
                            max(0, prompt_chars),
                            max(0, completion_chars),
                        ),
                    )
                    cur.execute(
                        """
                        INSERT INTO client_usage
                          (day, client_id, tier, requests, cache_hits, prompt_chars, completion_chars)
                        VALUES (%s, %s, %s, 1, %s, %s, %s)
                        ON CONFLICT (day, client_id, tier) DO UPDATE SET
                            requests = client_usage.requests + 1,
                            cache_hits = client_usage.cache_hits + EXCLUDED.cache_hits,
                            prompt_chars = client_usage.prompt_chars + EXCLUDED.prompt_chars,
                            completion_chars = client_usage.completion_chars
                              + EXCLUDED.completion_chars
                        """,
                        (
                            day or _today(),
                            client_id or "unknown",
                            tier,
                            1 if cache_hit else 0,
                            max(0, prompt_chars),
                            max(0, completion_chars),
                        ),
                    )
                    cur.execute(
                        """
                        INSERT INTO user_usage
                          (day, client_id, user_id, tier, requests, cache_hits,
                           prompt_chars, completion_chars)
                        VALUES (%s, %s, %s, %s, 1, %s, %s, %s)
                        ON CONFLICT (day, client_id, user_id, tier) DO UPDATE SET
                            requests = user_usage.requests + 1,
                            cache_hits = user_usage.cache_hits + EXCLUDED.cache_hits,
                            prompt_chars = user_usage.prompt_chars + EXCLUDED.prompt_chars,
                            completion_chars = user_usage.completion_chars
                              + EXCLUDED.completion_chars
                        """,
                        (
                            day or _today(),
                            client_id or "unknown",
                            user_id or "unknown",
                            tier,
                            1 if cache_hit else 0,
                            max(0, prompt_chars),
                            max(0, completion_chars),
                        ),
                    )
                conn.commit()
        except Exception:
            pass

    def by_client(
        self, days: int = 7, *, frontier_price_per_1k_tokens: float = 0.002
    ) -> list[dict[str, Any]]:
        if not self.enabled:
            return []
        cutoff = (datetime.now(timezone.utc) - timedelta(days=max(0, days - 1))).strftime(
            "%Y-%m-%d"
        )
        try:
            with self._lock, self._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT client_id, tier, SUM(requests), SUM(cache_hits),"
                        " SUM(prompt_chars), SUM(completion_chars)"
                        " FROM client_usage WHERE day >= %s GROUP BY client_id, tier",
                        (cutoff,),
                    )
                    rows = cur.fetchall()
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

    def by_user(
        self, days: int = 7, *, frontier_price_per_1k_tokens: float = 0.002
    ) -> list[dict[str, Any]]:
        if not self.enabled:
            return []
        cutoff = (datetime.now(timezone.utc) - timedelta(days=max(0, days - 1))).strftime(
            "%Y-%m-%d"
        )
        try:
            with self._lock, self._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT client_id, user_id, tier, SUM(requests), SUM(cache_hits),"
                        " SUM(prompt_chars), SUM(completion_chars)"
                        " FROM user_usage WHERE day >= %s GROUP BY client_id, user_id, tier",
                        (cutoff,),
                    )
                    rows = cur.fetchall()
        except Exception:
            return []
        users: dict[tuple[str, str], dict[str, Any]] = {}
        for client_id, user_id, tier, requests, cache_hits, prompt_chars, completion_chars in rows:
            key = (client_id, user_id)
            entry = users.setdefault(
                key,
                {
                    "client_id": client_id,
                    "user_id": user_id,
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
        for entry in users.values():
            entry["estimated_saved_usd"] = round(entry["estimated_saved_usd"], 4)
        return sorted(users.values(), key=lambda entry: -entry["requests"])

    def frontier_spend_usd_for_user(
        self,
        client_id: str,
        user_id: str,
        *,
        window: str = "day",
        pricing: Any = None,
        fallback_per_1k: float = 0.002,
        day: str | None = None,
        month: str | None = None,
        price_per_1k_tokens: float | None = None,
    ) -> float:
        del pricing  # Postgres ledger prices by chars/4 only
        if not self.enabled or not client_id or not user_id:
            return 0.0
        rate = fallback_per_1k if price_per_1k_tokens is None else price_per_1k_tokens
        if window == "month":
            where, params = "client_id = %s AND user_id = %s AND day LIKE %s AND tier = %s", (
                client_id,
                user_id,
                (month or _today()[:7]) + "-%",
                FRONTIER_TIER,
            )
        elif window == "day":
            where, params = "client_id = %s AND user_id = %s AND day = %s AND tier = %s", (
                client_id,
                user_id,
                day or _today(),
                FRONTIER_TIER,
            )
        else:
            raise ValueError(f"window must be 'day' or 'month', got {window!r}")
        try:
            with self._lock, self._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT COALESCE(SUM(prompt_chars + completion_chars), 0)"
                        f" FROM user_usage WHERE {where}",
                        params,
                    )
                    row = cur.fetchone()
        except Exception:
            return 0.0
        chars = row[0] if row else 0
        return (chars / 4) / 1000 * rate

    def frontier_spend_usd(self, *, price_per_1k_tokens: float, day: str | None = None) -> float:
        if not self.enabled:
            return 0.0
        try:
            with self._lock, self._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT COALESCE(SUM(prompt_chars + completion_chars), 0)"
                        " FROM usage WHERE day = %s AND tier = %s",
                        (day or _today(), FRONTIER_TIER),
                    )
                    row = cur.fetchone()
        except Exception:
            return 0.0
        chars = row[0] if row else 0
        return (chars / 4) / 1000 * price_per_1k_tokens

    def frontier_spend_usd_month(
        self, *, price_per_1k_tokens: float, month: str | None = None
    ) -> float:
        if not self.enabled:
            return 0.0
        prefix = (month or _today()[:7]) + "-%"
        try:
            with self._lock, self._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT COALESCE(SUM(prompt_chars + completion_chars), 0)"
                        " FROM usage WHERE day LIKE %s AND tier = %s",
                        (prefix, FRONTIER_TIER),
                    )
                    row = cur.fetchone()
        except Exception:
            return 0.0
        chars = row[0] if row else 0
        return (chars / 4) / 1000 * price_per_1k_tokens

    def report(self, days: int = 7, *, frontier_price_per_1k_tokens: float = 0.002) -> dict[str, Any]:
        if not self.enabled:
            return {"enabled": False, "days": [], "totals": _empty_totals()}
        cutoff = (datetime.now(timezone.utc) - timedelta(days=max(0, days - 1))).strftime("%Y-%m-%d")
        try:
            with self._lock, self._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT day, tier, requests, cache_hits, prompt_chars, completion_chars"
                        " FROM usage WHERE day >= %s ORDER BY day",
                        (cutoff,),
                    )
                    rows = cur.fetchall()
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
            entry["tiers"][tier] = {
                "requests": requests,
                "cache_hits": cache_hits,
                "prompt_chars": prompt_chars,
                "completion_chars": completion_chars,
            }
            totals["requests"] += requests
            totals["cache_hits"] += cache_hits
            if tier == FRONTIER_TIER:
                totals["frontier_requests"] += requests
            else:
                totals["local_requests"] += requests
                tokens = (prompt_chars + completion_chars) / 4
                totals["estimated_saved_usd"] += tokens / 1000 * frontier_price_per_1k_tokens
        totals["estimated_saved_usd"] = round(totals["estimated_saved_usd"], 4)
        return {"enabled": True, "days": list(per_day.values()), "totals": totals}

    def get_budget_window_state(
        self, scope: str, scope_id: str, duration: str
    ) -> dict[str, Any] | None:
        if not self.enabled:
            return None
        try:
            with self._lock, self._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT period_id, carry_usd FROM budget_window_state"
                        " WHERE scope = %s AND scope_id = %s AND duration = %s",
                        (scope, scope_id, duration),
                    )
                    row = cur.fetchone()
        except Exception:
            return None
        if row is None:
            return None
        return {"period_id": row[0], "carry_usd": float(row[1] or 0.0)}

    def put_budget_window_state(
        self,
        scope: str,
        scope_id: str,
        duration: str,
        *,
        period_id: str,
        carry_usd: float,
    ) -> None:
        if not self.enabled:
            return
        try:
            with self._lock, self._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO budget_window_state
                            (scope, scope_id, duration, period_id, carry_usd)
                        VALUES (%s, %s, %s, %s, %s)
                        ON CONFLICT (scope, scope_id, duration) DO UPDATE SET
                            period_id = EXCLUDED.period_id,
                            carry_usd = EXCLUDED.carry_usd
                        """,
                        (scope, scope_id, duration, period_id, float(carry_usd)),
                    )
                conn.commit()
        except Exception:
            pass

    def prune_before_day(self, cutoff_day: str, *, dry_run: bool = False) -> int:
        if not self.enabled:
            return 0
        try:
            with self._lock, self._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT COUNT(*) FROM usage WHERE day < %s", (cutoff_day,))
                    usage = cur.fetchone()[0]
                    cur.execute(
                        "SELECT COUNT(*) FROM client_usage WHERE day < %s", (cutoff_day,)
                    )
                    clients = cur.fetchone()[0]
                    cur.execute(
                        "SELECT COUNT(*) FROM user_usage WHERE day < %s", (cutoff_day,)
                    )
                    users = cur.fetchone()[0]
                    if not dry_run and (usage or clients or users):
                        cur.execute("DELETE FROM usage WHERE day < %s", (cutoff_day,))
                        cur.execute("DELETE FROM client_usage WHERE day < %s", (cutoff_day,))
                        cur.execute("DELETE FROM user_usage WHERE day < %s", (cutoff_day,))
                conn.commit()
                return int(usage) + int(clients) + int(users)
        except Exception:
            return 0
