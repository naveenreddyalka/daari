"""Signed completion webhooks for /v1/batches jobs (#2069).

Mirrors ``responses_webhooks``: reuses ``sign_webhook`` /
``signature_header_value``, Redis SET NX fleet dedupe (fail-open), and
``assert_offline_url_allowed(..., surface="webhook")``.
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

REDIS_KEY_PREFIX = "daari:batch-webhook:"
DEFAULT_CLAIM_TTL_SECONDS = 86_400
DEFAULT_MAX_ATTEMPTS = 2
DEFAULT_RETRY_BACKOFF_SECONDS = 0.25

_pending: list[threading.Thread] = []
_pending_lock = threading.Lock()


def batch_completion_payload(stored: dict[str, Any]) -> dict[str, Any]:
    """Minimal completion notify body: id, status, request_counts."""
    payload: dict[str, Any] = {
        "id": stored.get("id"),
        "status": stored.get("status"),
    }
    counts = stored.get("request_counts")
    if isinstance(counts, dict):
        payload["request_counts"] = {
            key: counts[key]
            for key in ("total", "completed", "failed", "skipped")
            if key in counts
        }
    return payload


def _record_result(metrics: Any, result: str) -> None:
    if metrics is None or not hasattr(metrics, "record_batch_webhook"):
        return
    try:
        metrics.record_batch_webhook(result)
    except Exception:  # noqa: BLE001 — metrics must not break notify
        return


def _redis_client(redis: Any, redis_url: str, timeout_seconds: float = 2.0) -> Any:
    if redis is not None:
        return redis
    url = (redis_url or "").strip()
    if not url:
        return None
    from daari.cache.redis_client import connect_redis

    return connect_redis(url, timeout_seconds=timeout_seconds)


def claim_batch_webhook_delivery(
    batch_id: str,
    *,
    redis: Any = None,
    redis_url: str = "",
    ttl_seconds: int = DEFAULT_CLAIM_TTL_SECONDS,
) -> bool:
    """True when this replica should deliver. Redis errors fail open."""
    from daari.gateway.request_log import log_gateway_event

    bid = (batch_id or "").strip()
    if not bid:
        return True
    client = _redis_client(redis, redis_url)
    if client is None:
        return True
    key = f"{REDIS_KEY_PREFIX}{bid}"
    try:
        claimed = client.set(key, "1", nx=True, ex=int(ttl_seconds))
    except Exception as exc:  # noqa: BLE001 — fail open
        log_gateway_event(
            "batch.completion_webhook_dedupe_degraded",
            {
                "error": f"{type(exc).__name__}: {exc}",
                "id": bid,
            },
        )
        return True
    return bool(claimed)


def deliver_batch_completion_webhook(
    *,
    url: str,
    secret: str = "",
    previous_secret: str = "",
    body: dict[str, Any],
    transport: Any = None,
    timeout: float = 5.0,
    metrics: Any = None,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    retry_backoff_seconds: float = DEFAULT_RETRY_BACKOFF_SECONDS,
) -> str:
    """POST a signed batch completion payload with one retry on 5xx/transport.

    Failures log; never raise. Returns ``ok``, ``error``, or ``skipped``.
    """
    from daari.gateway.request_log import log_gateway_event

    target = (url or "").strip()
    if not target:
        _record_result(metrics, "skipped")
        return "skipped"
    payload = batch_completion_payload(body)
    content = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    headers: dict[str, str] = {"Content-Type": "application/json"}
    sec = (secret or "").strip()
    if sec:
        timestamp = str(int(time.time()))
        headers[TIMESTAMP_HEADER] = timestamp
        headers[SIGNATURE_HEADER] = signature_header_value(
            content,
            sec,
            timestamp,
            previous_secret=previous_secret,
        )
    attempts = max(1, int(max_attempts))
    last_exc: Exception | None = None
    for attempt in range(attempts):
        try:
            import httpx

            from daari.security.offline_mode import (
                apply_offline_event_hooks,
                assert_offline_url_allowed,
            )

            assert_offline_url_allowed(target, surface="webhook")
            client_kwargs = apply_offline_event_hooks(
                {"transport": transport, "timeout": timeout},
                sync=True,
            )
            with httpx.Client(**client_kwargs) as client:
                response = client.post(target, content=content, headers=headers)
                response.raise_for_status()
            _record_result(metrics, "ok")
            return "ok"
        except Exception as exc:  # noqa: BLE001 — best-effort notify
            last_exc = exc
            retryable = _is_retryable(exc)
            if attempt + 1 < attempts and retryable:
                if retry_backoff_seconds > 0:
                    time.sleep(float(retry_backoff_seconds))
                continue
            break
    log_gateway_event(
        "batch.completion_webhook_failed",
        {
            "error": f"{type(last_exc).__name__}: {last_exc}" if last_exc else "unknown",
            "id": payload.get("id"),
            "status": payload.get("status"),
            "attempts": attempts,
        },
    )
    _record_result(metrics, "error")
    return "error"


def _is_retryable(exc: Exception) -> bool:
    try:
        import httpx
    except ImportError:
        return True
    if isinstance(exc, (httpx.TransportError, httpx.TimeoutException)):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        status = int(exc.response.status_code)
        return status >= 500
    # OfflineEgressBlocked and 4xx are not retryable
    return False


def schedule_batch_completion_webhook(
    *,
    url: str,
    secret: str = "",
    previous_secret: str = "",
    body: dict[str, Any],
    transport: Any = None,
    timeout: float = 5.0,
    redis: Any = None,
    redis_url: str = "",
    metrics: Any = None,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    retry_backoff_seconds: float = DEFAULT_RETRY_BACKOFF_SECONDS,
) -> threading.Thread:
    """Claim + deliver on a daemon thread so the event loop is never blocked."""

    def _run() -> None:
        bid = str((body or {}).get("id") or "")
        if not claim_batch_webhook_delivery(bid, redis=redis, redis_url=redis_url):
            _record_result(metrics, "deduped")
            return
        deliver_batch_completion_webhook(
            url=url,
            secret=secret,
            previous_secret=previous_secret,
            body=body,
            transport=transport,
            timeout=timeout,
            metrics=metrics,
            max_attempts=max_attempts,
            retry_backoff_seconds=retry_backoff_seconds,
        )

    thread = threading.Thread(target=_run, daemon=True, name="daari-batch-webhook")
    with _pending_lock:
        _pending.append(thread)
    thread.start()
    return thread


def wait_batch_webhooks(timeout: float = 5.0) -> None:
    """Join scheduled delivery threads (tests)."""
    deadline = time.monotonic() + float(timeout)
    while True:
        with _pending_lock:
            threads = [t for t in _pending if t.is_alive()]
            _pending[:] = threads
        if not threads:
            return
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return
        for thread in threads:
            thread.join(timeout=max(0.01, remaining / max(len(threads), 1)))


def apply_batch_webhook_settings(store: Any, settings: Any, metrics: Any = None) -> None:
    """Copy AlertSettings batch webhook fields onto a BatchStore."""
    alerts = getattr(settings, "alerts", None)
    if alerts is None:
        store.completion_webhook_url = ""
        store.completion_webhook_secret = ""
        store.completion_webhook_secret_previous = ""
    else:
        store.completion_webhook_url = (
            getattr(alerts, "batches_completion_webhook_url", "")
            or getattr(alerts, "batch_completion_webhook_url", "")
            or ""
        )
        store.completion_webhook_secret = (
            getattr(alerts, "batches_completion_webhook_secret", "")
            or getattr(alerts, "batch_completion_webhook_secret", "")
            or ""
        )
        store.completion_webhook_secret_previous = (
            getattr(alerts, "batches_completion_webhook_secret_previous", "")
            or getattr(alerts, "batch_completion_webhook_secret_previous", "")
            or ""
        )
    redis_url = ""
    cache = getattr(settings, "cache", None)
    if cache is not None and str(getattr(cache, "backend", "") or "") == "redis":
        redis_url = str(getattr(cache, "redis_url", "") or "")
    store.completion_webhook_redis_url = redis_url
    if metrics is not None:
        store.completion_webhook_metrics = metrics
    elif not hasattr(store, "completion_webhook_metrics"):
        store.completion_webhook_metrics = None
