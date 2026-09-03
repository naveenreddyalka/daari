"""Budget threshold webhooks (#333).

When a request pushes a key/team window across a configured ratio, POST a
JSON payload to `alerts.budget_webhook_url`. Delivery is best-effort and
never delays the response. Dedupe is in-process (one fire per
scope/window/threshold until the window resets); multi-replica installs can
double-notify.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any, Iterable

from daari.auth.budgets import WindowStatus, window_label
from daari.auth.virtual_keys import Team, VirtualKey

DEFAULT_THRESHOLDS = (0.8, 1.0)


def _ratio(status: WindowStatus) -> float:
    cap = float(status.window.max_usd)
    if cap <= 0:
        return 0.0
    return float(status.spend) / cap


def _identity(status: WindowStatus, key: VirtualKey, team: Team | None) -> tuple[str, str, str]:
    if status.scope == "team" and team is not None:
        return "team", team.team_id, team.name
    return "key", key.key_id, key.name


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
    _seen: set[tuple[str, str, str, float, int]] = field(default_factory=set)
    _lock: threading.Lock = field(default_factory=threading.Lock)

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
            "limit_usd": float(status.window.max_usd),
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
