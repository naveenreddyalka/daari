"""Budget threshold webhooks (#333, #369, #484, #498).

When a request pushes a key/team window across a configured ratio, POST a
JSON payload to `alerts.budget_webhook_url`. Delivery is best-effort and
never delays the response. Dedupe is in-process (one fire per
scope/window/threshold until the window resets). When the same Redis the
cache and rate limits use is configured, a crossing is claimed with
`SET NX EX` before delivery so a fleet notifies once; Redis errors still
deliver and log `budget.alert_dedupe_degraded`.

USD and request-count quotas (#467) both alert: crossings key by
`(scope, duration, quota)` so a shared duration still pages twice when both
dimensions trip. Request payloads use `quota: "requests"` with
`limit_requests` / `spent_requests` / `remaining_requests` instead of USD fields.

When `alerts.budget_webhook_secret` is set, POSTs carry `X-Daari-Timestamp`
and `X-Daari-Signature` (HMAC-SHA256 over ``timestamp + "." + body``).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable

from daari.auth.budgets import BudgetWindow, WindowStatus, window_label
from daari.auth.virtual_keys import Team, VirtualKey

DEFAULT_THRESHOLDS = (0.8, 1.0)
DEFAULT_REPLAY_TOLERANCE_SECONDS = 300
REDIS_KEY_PREFIX = "daari:budget-alert:"
SIGNATURE_HEADER = "X-Daari-Signature"
TIMESTAMP_HEADER = "X-Daari-Timestamp"


def sign_webhook(body: bytes, secret: str, timestamp: str) -> str:
    """HMAC-SHA256 hex digest over ``timestamp + '.' + body`` (#484)."""
    return hmac.new(
        secret.encode(),
        f"{timestamp}.".encode() + body,
        hashlib.sha256,
    ).hexdigest()


def signature_header_value(
    body: bytes,
    secret: str,
    timestamp: str,
    *,
    previous_secret: str = "",
) -> str:
    """Build ``X-Daari-Signature``; include previous during rotation grace (#1680).

    Current secret is always first. When ``previous_secret`` is set, appends
    a second digest (Stripe-style dual ``v1``) so receivers can verify against
    either secret without a hard cutover.
    """
    primary = sign_webhook(body, secret, timestamp)
    prev = (previous_secret or "").strip()
    if not prev:
        return primary
    return f"{primary},{sign_webhook(body, prev, timestamp)}"


def _signature_candidates(signature_hex: str) -> list[str]:
    """Split a signature header into digests (plain or ``v1=`` Stripe form)."""
    out: list[str] = []
    for part in (signature_hex or "").split(","):
        token = part.strip().lower()
        if not token:
            continue
        if token.startswith("v1="):
            token = token[3:].strip()
        if token:
            out.append(token)
    return out


def verify_webhook_signature(
    body: bytes,
    signature_hex: str,
    secret: str,
    timestamp: str,
    *,
    previous_secret: str = "",
    now: int | None = None,
    tolerance_seconds: int = DEFAULT_REPLAY_TOLERANCE_SECONDS,
) -> bool:
    """Receiver-side check: HMAC match and timestamp within replay window.

    During secret rotation (#1680), pass ``previous_secret`` so either the
    current or previous signing key accepts the header (which may list both).
    """
    secrets = [s.strip() for s in (secret, previous_secret) if (s or "").strip()]
    if not secrets or not signature_hex or not timestamp:
        return False
    try:
        ts = int(timestamp)
    except (TypeError, ValueError):
        return False
    moment = int(time.time()) if now is None else int(now)
    if abs(moment - ts) > int(tolerance_seconds):
        return False
    candidates = _signature_candidates(signature_hex)
    if not candidates:
        return False
    for sec in secrets:
        expected = sign_webhook(body, sec, timestamp)
        for cand in candidates:
            if hmac.compare_digest(expected, cand):
                return True
    return False


def _ratio(status: WindowStatus) -> float:
    cap = float(status.limit)
    if cap <= 0:
        return 0.0
    return float(status.spend) / cap


def _identity(status: WindowStatus, key: VirtualKey, team: Team | None) -> tuple[str, str, str]:
    if status.scope == "team" and team is not None:
        return "team", team.team_id, team.name
    if status.scope == "model":
        # Pattern is the identity — never collapse onto the key id (#1807).
        pattern = (getattr(status, "model_pattern", None) or "").strip() or "model"
        return "model", pattern, pattern
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


def _crossing_key(status: WindowStatus) -> tuple[str, str, str, str]:
    """Scope + duration + quota (+ pattern) so USD/request and model caps alert (#498, #1807)."""
    pattern = (getattr(status, "model_pattern", None) or "").strip()
    return (
        status.scope,
        status.window.duration,
        getattr(status, "quota", "usd") or "usd",
        pattern,
    )


def crossings(
    before: Iterable[WindowStatus],
    after: Iterable[WindowStatus],
    thresholds: Iterable[float],
) -> list[tuple[WindowStatus, float]]:
    """Thresholds newly reached between two snapshots of the same windows."""
    prior = {_crossing_key(item): _ratio(item) for item in before}
    hits: list[tuple[WindowStatus, float]] = []
    marks = sorted({float(t) for t in thresholds if 0 < float(t) <= 1.0})
    for status in after:
        start = prior.get(_crossing_key(status), 0.0)
        end = _ratio(status)
        for threshold in marks:
            if start < threshold <= end:
                hits.append((status, threshold))
    return hits


@dataclass
class BudgetAlerter:
    webhook_url: str
    thresholds: tuple[float, ...] = DEFAULT_THRESHOLDS
    member_thresholds: tuple[float, ...] = ()
    webhook_secret: str = ""
    webhook_secret_previous: str = ""
    audit: Any | None = None
    metrics: Any | None = None
    transport: Any | None = None
    timeout: float = 3.0
    redis: Any | None = None
    redis_url: str = ""
    redis_timeout_seconds: float = 2.0
    _seen: set[tuple[str, str, str, float, int]] = field(default_factory=set)
    _lock: threading.Lock = field(default_factory=threading.Lock)
    _redis_client: Any | None = field(default=None, repr=False, compare=False)

    @property
    def enabled(self) -> bool:
        return bool(self.webhook_url.strip())

    @property
    def signing_enabled(self) -> bool:
        return bool(self.webhook_secret.strip())

    def _dedupe_key(
        self, status: WindowStatus, scope_id: str, threshold: float
    ) -> tuple[str, str, str, float, int]:
        # Include quota in the window stamp so USD + request alerts dedupe independently.
        label = window_label(status.window.duration)
        quota = getattr(status, "quota", "usd") or "usd"
        if quota != "usd":
            label = f"{label}:{quota}"
        return (
            status.scope,
            scope_id,
            label,
            float(threshold),
            status.reset_epoch,
        )

    def _redis_enabled(self) -> bool:
        return self.redis is not None or bool(self.redis_url)

    def _store(self) -> Any:
        if self.redis is not None:
            return self.redis
        if self._redis_client is None:
            from daari.cache.redis_client import connect_redis

            self._redis_client = connect_redis(
                self.redis_url, timeout_seconds=self.redis_timeout_seconds
            )
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
        base: dict[str, Any] = {
            "scope": scope,
            "id": scope_id,
            "name": name,
            "window": window_label(status.window.duration),
            "threshold": float(threshold),
            "reset_epoch": status.reset_epoch,
            "reset_at": status.reset_at,
        }
        if scope == "model":
            pattern = (getattr(status, "model_pattern", None) or "").strip()
            if pattern:
                base["model_pattern"] = pattern
        if getattr(status, "quota", "usd") == "requests":
            base["quota"] = "requests"
            base["limit_requests"] = int(status.limit)
            base["spent_requests"] = int(status.spend)
            base["remaining_requests"] = int(status.remaining)
            return base
        base["limit_usd"] = float(status.limit)
        base["spent_usd"] = round(float(status.spend), 6)
        base["remaining_usd"] = round(status.remaining, 6)
        return base

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

        headers: dict[str, str] = {}
        content: bytes | None = None
        json_body: dict[str, Any] | None = body
        if self.signing_enabled:
            # Serialize once so the HMAC covers the exact wire bytes (#484).
            content = json.dumps(body, separators=(",", ":"), sort_keys=True).encode()
            timestamp = str(int(time.time()))
            headers[TIMESTAMP_HEADER] = timestamp
            headers[SIGNATURE_HEADER] = signature_header_value(
                content,
                self.webhook_secret,
                timestamp,
                previous_secret=self.webhook_secret_previous,
            )
            headers["Content-Type"] = "application/json"
            json_body = None
        try:
            import httpx

            with httpx.Client(transport=self.transport, timeout=self.timeout) as client:
                response = client.post(
                    self.webhook_url,
                    content=content,
                    json=json_body,
                    headers=headers or None,
                )
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

    def notify_member(
        self,
        before_spend: float,
        after_spend: float,
        *,
        key: VirtualKey,
        team: Team | None,
        user_id: str,
        limit_usd: float | None = None,
        now: datetime | None = None,
    ) -> list[dict[str, Any]]:
        """POST when one end-user crosses a share of ``user_daily_usd_cap`` (#1633).

        Empty ``member_thresholds`` is a no-op so key/team alerts stay unchanged.
        Dedupe is once per team member, daily window, and threshold.
        """
        if not self.enabled or not self.member_thresholds:
            return []
        member = (user_id or "").strip()
        if team is None or not member:
            return []
        cap = float(key.user_daily_usd_cap if limit_usd is None else limit_usd)
        if cap <= 0:
            return []
        moment = now or datetime.now(timezone.utc)
        window = BudgetWindow("day", cap)
        before = WindowStatus(window=window, scope="user", spend=float(before_spend), now=moment)
        after = WindowStatus(window=window, scope="user", spend=float(after_spend), now=moment)
        out: list[dict[str, Any]] = []
        for status, threshold in crossings([before], [after], self.member_thresholds):
            stamp = self._dedupe_key(status, f"{team.team_id}:{member}", threshold)
            stamp = ("member", stamp[1], stamp[2], stamp[3], stamp[4])
            with self._lock:
                if stamp in self._seen:
                    continue
                self._seen.add(stamp)
            if self._redis_enabled() and not self._claim_redis(stamp, status):
                continue
            out.append(
                {
                    "scope": "member",
                    "id": member,
                    "team_id": team.team_id,
                    "user_id": member,
                    "name": member,
                    "window": window_label(status.window.duration),
                    "threshold": float(threshold),
                    "limit": float(status.limit),
                    "spent": round(float(status.spend), 6),
                    "limit_usd": float(status.limit),
                    "spent_usd": round(float(status.spend), 6),
                    "remaining_usd": round(status.remaining, 6),
                    "reset_epoch": status.reset_epoch,
                    "reset_at": status.reset_at,
                }
            )
        for body in out:
            self.deliver(body)
        return out


def _json_body_field(raw: bytes, field: str) -> str:
    """String field from a JSON object body; empty when absent or unreadable."""
    if not raw:
        return ""
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError, TypeError, ValueError):
        return ""
    if not isinstance(parsed, dict):
        return ""
    value = parsed.get(field)
    if value is None:
        return ""
    return str(value).strip()


def user_id_from_body(raw: bytes) -> str:
    """OpenAI ``user`` field from a JSON body; empty when absent or unreadable."""
    return _json_body_field(raw, "user")


def model_from_body(raw: bytes) -> str:
    """OpenAI ``model`` field from a JSON body; empty when absent or unreadable."""
    return _json_body_field(raw, "model")
