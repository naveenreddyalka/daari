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

FRONTIER_TIER = "L6"

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
"""


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
            except Exception:
                self.enabled = False

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path, timeout=5.0)

    def record(
        self,
        *,
        tier: str,
        cache_hit: bool = False,
        prompt_chars: int = 0,
        completion_chars: int = 0,
        day: str | None = None,
        client_id: str | None = None,
    ) -> None:
        if not self.enabled:
            return
        try:
            with self._lock, self._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO usage (day, tier, requests, cache_hits, prompt_chars, completion_chars)
                    VALUES (?, ?, 1, ?, ?, ?)
                    ON CONFLICT(day, tier) DO UPDATE SET
                        requests = requests + 1,
                        cache_hits = cache_hits + excluded.cache_hits,
                        prompt_chars = prompt_chars + excluded.prompt_chars,
                        completion_chars = completion_chars + excluded.completion_chars
                    """,
                    (
                        day or _today(),
                        tier,
                        1 if cache_hit else 0,
                        max(0, prompt_chars),
                        max(0, completion_chars),
                    ),
                )
                conn.execute(
                    """
                    INSERT INTO client_usage (day, client_id, tier, requests, cache_hits, prompt_chars, completion_chars)
                    VALUES (?, ?, ?, 1, ?, ?, ?)
                    ON CONFLICT(day, client_id, tier) DO UPDATE SET
                        requests = requests + 1,
                        cache_hits = cache_hits + excluded.cache_hits,
                        prompt_chars = prompt_chars + excluded.prompt_chars,
                        completion_chars = completion_chars + excluded.completion_chars
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

    def frontier_spend_usd(self, *, price_per_1k_tokens: float, day: str | None = None) -> float:
        """Estimated USD spent on the frontier tier for the given UTC day."""
        if not self.enabled:
            return 0.0
        try:
            with self._lock, self._connect() as conn:
                row = conn.execute(
                    "SELECT COALESCE(SUM(prompt_chars + completion_chars), 0)"
                    " FROM usage WHERE day = ? AND tier = ?",
                    (day or _today(), FRONTIER_TIER),
                ).fetchone()
        except Exception:
            return 0.0
        chars = row[0] if row else 0
        return (chars / 4) / 1000 * price_per_1k_tokens

    def frontier_spend_usd_month(
        self, *, price_per_1k_tokens: float, month: str | None = None
    ) -> float:
        """Estimated USD spent on L6 for the given UTC month (Trust PRD T5a)."""
        if not self.enabled:
            return 0.0
        prefix = (month or _today()[:7]) + "-%"
        try:
            with self._lock, self._connect() as conn:
                row = conn.execute(
                    "SELECT COALESCE(SUM(prompt_chars + completion_chars), 0)"
                    " FROM usage WHERE day LIKE ? AND tier = ?",
                    (prefix, FRONTIER_TIER),
                ).fetchone()
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
                # chars/4 ~ tokens, priced as if a frontier model had served them.
                tokens = (prompt_chars + completion_chars) / 4
                totals["estimated_saved_usd"] += tokens / 1000 * frontier_price_per_1k_tokens
        totals["estimated_saved_usd"] = round(totals["estimated_saved_usd"], 4)
        return {"enabled": True, "days": list(per_day.values()), "totals": totals}
