"""Opt-in virtual-key expiry webhooks (#1546).

When a key enters the ``expiring_soon`` window (``alerts.key_expiry_warn_days``,
default 14), POST a JSON payload to ``alerts.key_expiry_webhook_url``. Delivery
is best-effort. Dedupe is in-process (one fire per ``key_id`` + ``expires_at``).
When Redis is configured, a crossing is claimed with ``SET NX EX`` before
delivery so a fleet notifies once; Redis errors still deliver and log
``key_expiry.alert_dedupe_degraded``.

Signing reuses the budget-alert convention: ``X-Daari-Timestamp`` +
``X-Daari-Signature`` (HMAC-SHA256 over ``timestamp + "." + body``).
"""

from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable

from daari.auth.virtual_keys import VirtualKey, key_expiry_bucket
from daari.observability.budget_alerts import (
    SIGNATURE_HEADER,
    TIMESTAMP_HEADER,
    signature_header_value,
)

REDIS_KEY_PREFIX = "daari:key-expiry-alert:"


def redis_dedupe_key(key_id: str, expires_at: str) -> str:
    return f"{REDIS_KEY_PREFIX}{key_id}:{expires_at}"


def dedupe_ttl_seconds(expires_at: str, *, now: datetime | None = None) -> int:
    """Seconds until the key expires; floor 1 so a just-expired stamp still claims."""
    moment = now or datetime.now(timezone.utc)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    try:
        when = datetime.fromisoformat(str(expires_at).replace("Z", "+00:00"))
    except ValueError:
        return 86400
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    ttl = int(when.timestamp()) - int(moment.timestamp())
    return max(1, ttl)


@dataclass
class KeyExpiryAlerter:
    webhook_url: str
    warn_days: int = 14
    webhook_secret: str = ""
    webhook_secret_previous: str = ""
    audit: Any | None = None
    metrics: Any | None = None
    transport: Any | None = None
    timeout: float = 3.0
    redis: Any | None = None
    redis_url: str = ""
    redis_timeout_seconds: float = 2.0
    _seen: set[tuple[str, str]] = field(default_factory=set)
    _lock: threading.Lock = field(default_factory=threading.Lock)
    _redis_client: Any | None = field(default=None, repr=False, compare=False)

    @property
    def enabled(self) -> bool:
        return bool(self.webhook_url.strip())

    @property
    def signing_enabled(self) -> bool:
        return bool(self.webhook_secret.strip())

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

    def _claim_redis(self, key_id: str, expires_at: str, *, now: datetime) -> bool:
        """True when this replica should deliver. Errors deliver anyway."""
        from daari.gateway.request_log import log_gateway_event

        try:
            claimed = self._store().set(
                redis_dedupe_key(key_id, expires_at),
                "1",
                nx=True,
                ex=dedupe_ttl_seconds(expires_at, now=now),
            )
        except Exception as exc:
            log_gateway_event(
                "key_expiry.alert_dedupe_degraded",
                {
                    "error": f"{type(exc).__name__}: {exc}",
                    "key_id": key_id,
                },
            )
            return True
        return bool(claimed)

    def payload(self, key: VirtualKey) -> dict[str, Any]:
        return {
            "event": "key_expiry",
            "status": "expiring_soon",
            "key_id": key.key_id,
            "name": key.name,
            "expires_at": key.expires_at,
            "warn_days": int(self.warn_days),
        }

    def pending(
        self,
        keys: Iterable[VirtualKey],
        *,
        now: datetime | None = None,
    ) -> list[dict[str, Any]]:
        if not self.enabled:
            return []
        moment = now or datetime.now(timezone.utc)
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=timezone.utc)
        out: list[dict[str, Any]] = []
        for key in keys:
            if key_expiry_bucket(key, now=moment, warn_days=self.warn_days) != "expiring_soon":
                continue
            expires_at = str(key.expires_at or "")
            if not expires_at:
                continue
            stamp = (key.key_id, expires_at)
            with self._lock:
                if stamp in self._seen:
                    continue
                self._seen.add(stamp)
            if self._redis_enabled() and not self._claim_redis(
                key.key_id, expires_at, now=moment
            ):
                continue
            out.append(self.payload(key))
        return out

    def deliver(self, body: dict[str, Any]) -> None:
        from daari.gateway.request_log import log_gateway_event

        headers: dict[str, str] = {}
        content: bytes | None = None
        json_body: dict[str, Any] | None = body
        if self.signing_enabled:
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

            from daari.security.offline_mode import (
                apply_offline_event_hooks,
                assert_offline_url_allowed,
            )

            assert_offline_url_allowed(self.webhook_url, surface="webhook")
            client_kwargs = apply_offline_event_hooks(
                {"transport": self.transport, "timeout": self.timeout},
                sync=True,
            )
            with httpx.Client(**client_kwargs) as client:
                response = client.post(
                    self.webhook_url,
                    content=content,
                    json=json_body,
                    headers=headers or None,
                )
                response.raise_for_status()
        except Exception as exc:
            log_gateway_event(
                "key_expiry.alert_failed",
                {
                    "error": f"{type(exc).__name__}: {exc}",
                    "key_id": body.get("key_id"),
                    "name": body.get("name"),
                },
            )
            return
        log_gateway_event(
            "key_expiry.alert",
            {
                "key_id": body.get("key_id"),
                "name": body.get("name"),
                "expires_at": body.get("expires_at"),
            },
        )
        if self.audit is not None:
            self.audit.record(
                actor=str(body.get("key_id") or "unknown"),
                role="system",
                action="key_expiry.alert",
                detail={k: body[k] for k in body},
            )

    def notify(
        self,
        keys: Iterable[VirtualKey],
        *,
        now: datetime | None = None,
    ) -> list[dict[str, Any]]:
        payloads = self.pending(keys, now=now)
        for body in payloads:
            self.deliver(body)
        return payloads
