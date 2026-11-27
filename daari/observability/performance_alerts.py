"""On-box spike alerts versus the prior seven days (#2360).

Compares the last 24 hours to the daily baseline of the seven days before
that for frontier spend, request count, p95 latency, and 5xx rate. Drops
are ignored. A kind fires once per resource and window; later scrapes in
the same window do not send another webhook.
"""

from __future__ import annotations

import json
import math
import sqlite3
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

from daari.observability.budget_alerts import (
    SIGNATURE_HEADER,
    TIMESTAMP_HEADER,
    signature_header_value,
)

RESOURCE_FLEET = "fleet"
KINDS = ("spend", "traffic", "latency", "error_rate")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _iso(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")


def _parse(ts: str) -> datetime:
    text = (ts or "").replace("Z", "+00:00")
    moment = datetime.fromisoformat(text)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc)


def _p95(values: list[int]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    rank = max(1, math.ceil(0.95 * len(ordered)))
    return float(ordered[rank - 1])


def _windows(now: datetime) -> tuple[datetime, datetime, datetime]:
    recent_start = now - timedelta(hours=24)
    baseline_start = recent_start - timedelta(days=7)
    return baseline_start, recent_start, now


class PerformanceLedger:
    """SQLite samples for the spike detector. Best-effort writes."""

    def __init__(self, path: str | Path, *, enabled: bool = True) -> None:
        self.path = Path(path).expanduser()
        self.enabled = enabled
        self._lock = threading.Lock()
        self._last_scan = 0.0
        if self.enabled:
            self._ensure()

    def _ensure(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock, sqlite3.connect(self.path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS performance_samples (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts TEXT NOT NULL,
                    cost_usd REAL NOT NULL DEFAULT 0,
                    latency_ms INTEGER NOT NULL DEFAULT 0,
                    error INTEGER NOT NULL DEFAULT 0,
                    frontier INTEGER NOT NULL DEFAULT 0,
                    resource TEXT NOT NULL DEFAULT 'fleet'
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS performance_alert_fires (
                    resource TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    window_id TEXT NOT NULL,
                    PRIMARY KEY (resource, kind, window_id)
                )
                """
            )

    def record(
        self,
        *,
        ts: datetime | str | None = None,
        cost_usd: float = 0.0,
        latency_ms: int = 0,
        error: bool = False,
        frontier: bool = False,
        resource: str = RESOURCE_FLEET,
    ) -> None:
        if not self.enabled:
            return
        if isinstance(ts, datetime):
            stamp = _iso(ts)
        elif isinstance(ts, str) and ts.strip():
            stamp = _iso(_parse(ts))
        else:
            stamp = _iso(_utcnow())
        try:
            with self._lock, sqlite3.connect(self.path) as conn:
                conn.execute(
                    """
                    INSERT INTO performance_samples (
                        ts, cost_usd, latency_ms, error, frontier, resource
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        stamp,
                        float(cost_usd or 0.0),
                        max(0, int(latency_ms or 0)),
                        1 if error else 0,
                        1 if frontier else 0,
                        (resource or RESOURCE_FLEET).strip() or RESOURCE_FLEET,
                    ),
                )
        except Exception:
            return

    def _load(self, since: datetime) -> list[dict[str, Any]]:
        with self._lock, sqlite3.connect(self.path) as conn:
            rows = conn.execute(
                """
                SELECT ts, cost_usd, latency_ms, error, frontier, resource
                FROM performance_samples
                WHERE ts >= ?
                """,
                (_iso(since),),
            ).fetchall()
        out: list[dict[str, Any]] = []
        for ts, cost, latency, error, frontier, resource in rows:
            out.append(
                {
                    "ts": _parse(str(ts)),
                    "cost_usd": float(cost or 0.0),
                    "latency_ms": int(latency or 0),
                    "error": bool(error),
                    "frontier": bool(frontier),
                    "resource": str(resource or RESOURCE_FLEET),
                }
            )
        return out

    def open_alerts(
        self,
        now: datetime | None = None,
        *,
        spend_ratio: float = 2.0,
        traffic_ratio: float = 2.0,
        latency_ratio: float = 1.5,
        error_rate_ratio: float = 2.0,
        min_baseline_requests: int = 20,
    ) -> list[dict[str, Any]]:
        """Spikes currently open. Empty when the kill switch is off."""
        if not self.enabled:
            return []
        moment = now or _utcnow()
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=timezone.utc)
        baseline_start, recent_start, recent_end = _windows(moment)
        try:
            samples = self._load(baseline_start)
        except Exception:
            return []
        ratios = {
            "spend": float(spend_ratio),
            "traffic": float(traffic_ratio),
            "latency": float(latency_ratio),
            "error_rate": float(error_rate_ratio),
        }
        by_resource: dict[str, list[dict[str, Any]]] = {}
        for sample in samples:
            by_resource.setdefault(sample["resource"], []).append(sample)
        alerts: list[dict[str, Any]] = []
        window_id = moment.strftime("%Y-%m-%d")
        floor = max(1, int(min_baseline_requests))
        for resource, rows in sorted(by_resource.items()):
            baseline = [row for row in rows if baseline_start <= row["ts"] < recent_start]
            recent = [row for row in rows if recent_start <= row["ts"] < recent_end]
            if len(baseline) < floor:
                continue
            alerts.extend(
                _spikes(
                    resource=resource,
                    window_id=window_id,
                    baseline=baseline,
                    recent=recent,
                    ratios=ratios,
                )
            )
        return alerts

    def claim(self, alert: dict[str, Any]) -> bool:
        """True the first time this resource/kind/window is claimed."""
        try:
            with self._lock, sqlite3.connect(self.path) as conn:
                existing = conn.execute(
                    """
                    SELECT 1 FROM performance_alert_fires
                    WHERE resource = ? AND kind = ? AND window_id = ?
                    """,
                    (alert["resource"], alert["kind"], alert["window"]),
                ).fetchone()
                if existing:
                    return False
                conn.execute(
                    """
                    INSERT INTO performance_alert_fires (resource, kind, window_id)
                    VALUES (?, ?, ?)
                    """,
                    (alert["resource"], alert["kind"], alert["window"]),
                )
                return True
        except Exception:
            return False


def _spikes(
    *,
    resource: str,
    window_id: str,
    baseline: list[dict[str, Any]],
    recent: list[dict[str, Any]],
    ratios: dict[str, float],
) -> list[dict[str, Any]]:
    days = 7.0
    base_spend = sum(row["cost_usd"] for row in baseline if row["frontier"]) / days
    recent_spend = sum(row["cost_usd"] for row in recent if row["frontier"])
    base_traffic = len(baseline) / days
    recent_traffic = float(len(recent))
    base_latency = _p95([row["latency_ms"] for row in baseline if row["latency_ms"] > 0])
    recent_latency = _p95([row["latency_ms"] for row in recent if row["latency_ms"] > 0])
    base_errors = sum(1 for row in baseline if row["error"])
    recent_errors = sum(1 for row in recent if row["error"])
    base_rate = base_errors / len(baseline) if baseline else 0.0
    recent_rate = recent_errors / len(recent) if recent else 0.0
    measured = {
        "spend": (recent_spend, base_spend),
        "traffic": (recent_traffic, base_traffic),
        "latency": (recent_latency, base_latency),
        "error_rate": (recent_rate, base_rate),
    }
    alerts: list[dict[str, Any]] = []
    for kind, (recent_value, baseline_value) in measured.items():
        ratio = ratios[kind]
        if baseline_value <= 0 or recent_value <= baseline_value * ratio:
            continue
        alerts.append(
            {
                "resource": resource,
                "kind": kind,
                "window": window_id,
                "recent": round(recent_value, 6),
                "baseline": round(baseline_value, 6),
                "ratio": round(recent_value / baseline_value, 4),
            }
        )
    return alerts


def alert_settings(settings: Any) -> dict[str, Any]:
    alerts = getattr(settings, "alerts", settings)
    return {
        "enabled": bool(getattr(alerts, "performance_enabled", True)),
        "webhook_url": str(getattr(alerts, "performance_webhook_url", "") or "").strip(),
        "webhook_secret": str(getattr(alerts, "performance_webhook_secret", "") or "").strip(),
        "spend_ratio": float(getattr(alerts, "performance_spend_ratio", 2.0) or 2.0),
        "traffic_ratio": float(getattr(alerts, "performance_traffic_ratio", 2.0) or 2.0),
        "latency_ratio": float(getattr(alerts, "performance_latency_ratio", 1.5) or 1.5),
        "error_rate_ratio": float(getattr(alerts, "performance_error_rate_ratio", 2.0) or 2.0),
        "min_baseline_requests": int(
            getattr(alerts, "performance_min_baseline_requests", 20) or 20
        ),
    }


def fire_new_alerts(
    ledger: PerformanceLedger,
    settings: Any,
    *,
    metrics: Any | None = None,
    now: datetime | None = None,
    poster: Callable[[bytes, dict[str, str]], None] | None = None,
) -> list[dict[str, Any]]:
    """Claim and deliver spikes that have not fired in this window."""
    dial = alert_settings(settings)
    if not dial["enabled"] or not ledger.enabled:
        return []
    open_alerts = ledger.open_alerts(
        now,
        spend_ratio=dial["spend_ratio"],
        traffic_ratio=dial["traffic_ratio"],
        latency_ratio=dial["latency_ratio"],
        error_rate_ratio=dial["error_rate_ratio"],
        min_baseline_requests=dial["min_baseline_requests"],
    )
    fired: list[dict[str, Any]] = []
    for alert in open_alerts:
        if not ledger.claim(alert):
            continue
        if metrics is not None and hasattr(metrics, "record_performance_alert"):
            metrics.record_performance_alert(alert["kind"])
        if dial["webhook_url"]:
            _post(alert, dial, poster)
        fired.append(alert)
    return fired


def maybe_fire(
    ledger: PerformanceLedger,
    settings: Any | None = None,
    *,
    metrics: Any | None = None,
    interval_seconds: float = 60.0,
    poster: Callable[[bytes, dict[str, str]], None] | None = None,
) -> list[dict[str, Any]]:
    """Throttle the request-path scan so quiet recovery is not re-posted."""
    source = settings if settings is not None else getattr(ledger, "source_settings", None)
    if source is None:
        return []
    now_mono = time.monotonic()
    if now_mono - ledger._last_scan < interval_seconds:
        return []
    ledger._last_scan = now_mono
    return fire_new_alerts(ledger, source, metrics=metrics, poster=poster)


def _post(
    alert: dict[str, Any],
    dial: dict[str, Any],
    poster: Callable[[bytes, dict[str, str]], None] | None,
) -> None:
    body = json.dumps(alert, separators=(",", ":"), sort_keys=True).encode()
    headers = {"Content-Type": "application/json"}
    secret = dial["webhook_secret"]
    if secret:
        timestamp = str(int(time.time()))
        headers[TIMESTAMP_HEADER] = timestamp
        headers[SIGNATURE_HEADER] = signature_header_value(body, secret, timestamp)
    try:
        if poster is not None:
            poster(body, headers)
            return
        import httpx

        from daari.security.offline_mode import assert_offline_url_allowed

        assert_offline_url_allowed(dial["webhook_url"])
        httpx.post(dial["webhook_url"], content=body, headers=headers, timeout=3.0)
    except Exception:
        return


def performance_ledger_from_settings(settings: Any) -> PerformanceLedger:
    dial = alert_settings(settings)
    spend = getattr(getattr(settings, "usage", None), "spend", None)
    raw = getattr(spend, "path", "") or "~/.daari/spend.sqlite"
    path = Path(str(raw)).expanduser().with_name("performance-alerts.sqlite")
    ledger = PerformanceLedger(path, enabled=dial["enabled"])
    ledger.source_settings = settings
    return ledger


def open_alerts_for_settings(
    ledger: PerformanceLedger,
    settings: Any,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    dial = alert_settings(settings)
    if not dial["enabled"]:
        return []
    return ledger.open_alerts(
        now,
        spend_ratio=dial["spend_ratio"],
        traffic_ratio=dial["traffic_ratio"],
        latency_ratio=dial["latency_ratio"],
        error_rate_ratio=dial["error_rate_ratio"],
        min_baseline_requests=dial["min_baseline_requests"],
    )
