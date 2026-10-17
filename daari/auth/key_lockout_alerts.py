"""Signed webhook when a key prefix locks (#1704).

Reuses the budget-alert signer (``X-Daari-Timestamp`` + ``X-Daari-Signature``).
Fires when ``alerts.budget_webhook_url`` is set, otherwise
``alerts.key_expiry_webhook_url``. In-process dedupe (and Redis ``SET NX``
when a client is passed) sends one notice per prefix until unlock or process
restart.
"""

from __future__ import annotations

import json
import threading
import time
from typing import Any

from daari.observability.budget_alerts import (
    SIGNATURE_HEADER,
    TIMESTAMP_HEADER,
    signature_header_value,
)

REDIS_KEY_PREFIX = "daari:key-lock-alert:"

_seen: set[str] = set()
_lock = threading.Lock()


def reset_key_locked_alerts() -> None:
    """Drop in-process dedupe state (tests)."""
    with _lock:
        _seen.clear()


def clear_key_locked_alert(prefix: str, *, redis: Any | None = None) -> None:
    """Allow a later lock of the same prefix to notify again."""
    shown = (prefix or "")[:10]
    with _lock:
        _seen.discard(shown)
    if redis is None or not shown:
        return
    try:
        delete = getattr(redis, "delete", None)
        if callable(delete):
            delete(f"{REDIS_KEY_PREFIX}{shown}")
    except Exception:
        from daari.gateway.request_log import log_gateway_event

        log_gateway_event(
            "auth.key_locked_alert_dedupe_degraded",
            {"op": "clear", "prefix": shown},
        )


def _destination(settings: Any) -> tuple[str, str, str]:
    alerts = getattr(settings, "alerts", None)
    budget_url = str(getattr(alerts, "budget_webhook_url", "") or "").strip()
    expiry_url = str(getattr(alerts, "key_expiry_webhook_url", "") or "").strip()
    if budget_url:
        return (
            budget_url,
            str(getattr(alerts, "budget_webhook_secret", "") or ""),
            str(getattr(alerts, "budget_webhook_secret_previous", "") or ""),
        )
    if expiry_url:
        return (
            expiry_url,
            str(getattr(alerts, "key_expiry_webhook_secret", "") or ""),
            str(getattr(alerts, "key_expiry_webhook_secret_previous", "") or ""),
        )
    return "", "", ""


def notify_key_locked(
    settings: Any,
    *,
    prefix: str,
    failures: int,
    retry_after: int,
    transport: Any | None = None,
    redis: Any | None = None,
    timeout: float = 3.0,
) -> bool:
    """POST one ``key_locked`` event. Returns True when a request was sent."""
    from daari.gateway.request_log import log_gateway_event

    url, secret, previous = _destination(settings)
    if not url:
        return False
    shown = (prefix or "anonymous")[:10]
    with _lock:
        if shown in _seen:
            return False
        _seen.add(shown)
    if redis is not None:
        try:
            claimed = redis.set(
                f"{REDIS_KEY_PREFIX}{shown}",
                "1",
                nx=True,
                ex=max(1, int(retry_after or 60)),
            )
            if not claimed:
                return False
        except Exception as exc:
            log_gateway_event(
                "auth.key_locked_alert_dedupe_degraded",
                {"error": f"{type(exc).__name__}: {exc}", "prefix": shown},
            )
    body = {
        "event": "key_locked",
        "prefix": shown,
        "failures": int(failures),
        "retry_after": int(retry_after),
    }
    content = json.dumps(body, separators=(",", ":"), sort_keys=True).encode()
    headers = {"Content-Type": "application/json"}
    if secret.strip():
        timestamp = str(int(time.time()))
        headers[TIMESTAMP_HEADER] = timestamp
        headers[SIGNATURE_HEADER] = signature_header_value(
            content,
            secret,
            timestamp,
            previous_secret=previous,
        )
    try:
        import httpx

        with httpx.Client(transport=transport, timeout=timeout) as client:
            response = client.post(url, content=content, headers=headers)
            response.raise_for_status()
    except Exception as exc:
        log_gateway_event(
            "auth.key_locked_alert_failed",
            {"error": f"{type(exc).__name__}: {exc}", "prefix": shown},
        )
        return False
    log_gateway_event("auth.key_locked_alert", {"prefix": shown, "failures": int(failures)})
    return True
