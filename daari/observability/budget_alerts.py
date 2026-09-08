"""Budget threshold webhooks (#333, #369).

When a request pushes a key/team window across a configured ratio, POST a
JSON payload to `alerts.budget_webhook_url`. Delivery is best-effort and
never delays the response. Dedupe is in-process (one fire per
scope/window/threshold until the window resets). When the same Redis the
cache and rate limits use is configured, a crossing is claimed with
`SET NX EX` before delivery so a fleet notifies once; Redis errors still
deliver and log `budget.alert_dedupe_degraded`.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable

from daari.auth.budgets import WindowStatus, window_label
from daari.auth.virtual_keys import Team, VirtualKey

DEFAULT_THRESHOLDS = (0.8, 1.0)
REDIS_KEY_PREFIX = "daari:budget-alert:"


def _ratio(status: WindowStatus) -> float:
    cap = float(status.limit)
    if cap <= 0:
        return 0.0
    return float(status.spend) / cap


def _identity(status: WindowStatus, key: VirtualKey, team: Team | None) -> tuple[str, str, str]:
    if status.scope == "team" and team is not None:
        return "team", team.team_id, team.name
    return "key", key.key_id, key.name


def redis_dedupe_key(stamp: tuple[str, str, str, float, int]) -> str:
    """Redis key for one `(scope, id, window, threshold, reset_epoch)` crossing."""
    scope, scope_id, window, threshold, reset_epoch = stamp
    return f"{REDIS_KEY_PREFIX}{scope}:{scope_id}:{window}:{threshold}:{reset_epoch}"


def dedupe_ttl_seconds(status: WindowStatus) -> int:
    """Seconds until the window reset; floor 1 so a just-expired stamp still claims."""
    moment = status.now or datetime.now(timezone.utc)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    ttl = int(status.reset_epoch) - int(moment.timestamp())
    return max(1, ttl)


def crossings(
    before: Iterable[WindowStatus],
    after: Iterable[WindowStatus],
    thresholds: Iterable[float],
) -> list[tuple[WindowStatus, float]]:
    """Thresholds newly reached between two snapshots of the same windows."""
    prior = {(item.scope, item.window.duration): _ratio(item) for item in before}
    hits: list[tuple[WindowStatus, float]] = []
    marks = sorted({float(t) for t in thresholds if 0 < float(t) <= 1.0})
    for status in after:
        start = prior.get((status.scope, status.window.duration), 0.0)
        end = _ratio(status)
        for threshold in marks:
            if start < threshold <= end:
                hits.append((status, threshold))
    return hits


@dataclass
class BudgetAlerter:
    webhook_url: str
    thresholds: tuple[float, ...] = DEFAULT_THRESHOLDS
    audit: Any | None = None
    metrics: Any | None = None
    transport: Any | None = None
    timeout: float = 3.0
    redis: Any | None = None
    redis_url: str = ""
    _seen: set[tuple[str, str, str, float, int]] = field(default_factory=set)
    _lock: threading.Lock = field(default_factory=threading.Lock)
    _redis_client: Any | None = field(default=None, repr=False, compare=False)

    @property
    def enabled(self) -> bool:
        return bool(self.webhook_url.strip())

    def _dedupe_key(
        self, status: WindowStatus, scope_id: str, threshold: float
    ) -> tuple[str, str, str, float, int]:
        return (
            status.scope,
            scope_id,
            window_label(status.window.duration),
            float(threshold),
            status.reset_epoch,
        )

    def _redis_enabled(self) -> bool:
        return self.redis is not None or bool(self.redis_url)

    def _store(self) -> Any:
        if self.redis is not None:
            return self.redis
        if self._redis_client is None:
            import redis

            self._redis_client = redis.Redis.from_url(self.redis_url, decode_responses=True)
        return self._redis_client

    def _claim_redis(
        self, stamp: tuple[str, str, str, float, int], status: WindowStatus
    ) -> bool:
        """True when this replica should deliver. Errors deliver anyway."""
        from daari.gateway.request_log import log_gateway_event

        try:
            claimed = self._store().set(
                redis_dedupe_key(stamp),
                "1",
                nx=True,
                ex=dedupe_ttl_seconds(status),
            )
        except Exception as exc:
            log_gateway_event(
                "budget.alert_dedupe_degraded",
                {
                    "error": f"{type(exc).__name__}: {exc}",
                    "scope": stamp[0],
                    "id": stamp[1],
                    "window": stamp[2],
                    "threshold": stamp[3],
                },
            )
            return True
        return bool(claimed)

    def payload(
        self,
        status: WindowStatus,
        threshold: float,
        *,
        key: VirtualKey,
        team: Team | None,
    ) -> dict[str, Any]:
        scope, scope_id, name = _identity(status, key, team)
        return {
            "scope": scope,
            "id": scope_id,
            "name": name,
            "window": window_label(status.window.duration),
            "limit_usd": float(status.limit),
            "spent_usd": round(float(status.spend), 6),
            "remaining_usd": round(status.remaining, 6),
            "threshold": float(threshold),
            "reset_epoch": status.reset_epoch,
        }

    def pending(
        self,
        before: Iterable[WindowStatus],
        after: Iterable[WindowStatus],
        *,
        key: VirtualKey,
        team: Team | None,
    ) -> list[dict[str, Any]]:
        if not self.enabled:
            return []
        out: list[dict[str, Any]] = []
        for status, threshold in crossings(before, after, self.thresholds):
            _scope, scope_id, _name = _identity(status, key, team)
            stamp = self._dedupe_key(status, scope_id, threshold)
            with self._lock:
                if stamp in self._seen:
                    continue
                self._seen.add(stamp)
            # Fleet claim stays off the response path: `notify` already runs
            # in a background thread from the gateway.
            if self._redis_enabled() and not self._claim_redis(stamp, status):
                continue
            out.append(self.payload(status, threshold, key=key, team=team))
        return out

    def deliver(self, body: dict[str, Any]) -> None:
        """POST one alert. Failures are logged; never raised to the caller."""
        from daari.gateway.request_log import log_gateway_event

        try:
            import httpx

            with httpx.Client(transport=self.transport, timeout=self.timeout) as client:
                response = client.post(self.webhook_url, json=body)
                response.raise_for_status()
        except Exception as exc:
            log_gateway_event(
                "budget.alert_failed",
                {
                    "error": f"{type(exc).__name__}: {exc}",
                    "scope": body.get("scope"),
                    "window": body.get("window"),
                    "threshold": body.get("threshold"),
                },
            )
            return
        log_gateway_event(
            "budget.alert",
            {
                "scope": body.get("scope"),
                "id": body.get("id"),
                "window": body.get("window"),
                "threshold": body.get("threshold"),
            },
        )
        if self.audit is not None:
            self.audit.record(
                actor=str(body.get("id") or "unknown"),
                role="system",
                action="budget.alert",
                detail={k: body[k] for k in body},
            )
        if self.metrics is not None:
            self.metrics.record_budget_alert(
                scope=str(body.get("scope") or "key"),
                threshold=float(body.get("threshold") or 0),
            )

    def notify(
        self,
        before: Iterable[WindowStatus],
        after: Iterable[WindowStatus],
        *,
        key: VirtualKey,
        team: Team | None,
    ) -> list[dict[str, Any]]:
        payloads = self.pending(before, after, key=key, team=team)
        for body in payloads:
            self.deliver(body)
        return payloads
