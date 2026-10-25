"""Signed completion webhooks for background Responses jobs (#1892, #1913).

Reuses ``sign_webhook`` / ``signature_header_value`` from budget alerts.
Empty URL soft-fails with no network call. Delivery runs off the caller's
thread with one retry on 5xx/transport errors; Redis SET NX claims a
response id so cancel+complete races fire once across a fleet.
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

REDIS_KEY_PREFIX = "daari:responses-webhook:"
DEFAULT_CLAIM_TTL_SECONDS = 86_400
DEFAULT_MAX_ATTEMPTS = 2
DEFAULT_RETRY_BACKOFF_SECONDS = 0.25

_pending: list[threading.Thread] = []
_pending_lock = threading.Lock()


def responses_completion_payload(stored: dict[str, Any]) -> dict[str, Any]:
    """Minimal OpenAI-shaped completion notify body."""
    payload: dict[str, Any] = {
        "id": stored.get("id"),
        "status": stored.get("status"),
        "model": stored.get("model"),
    }
    usage = stored.get("usage")
    if isinstance(usage, dict):
        payload["usage"] = {
            key: usage[key]
            for key in ("input_tokens", "output_tokens", "total_tokens")
            if key in usage
        }
    return payload


def _record_result(metrics: Any, result: str) -> None:
    if metrics is None or not hasattr(metrics, "record_responses_webhook"):
        return
    try:
        metrics.record_responses_webhook(result)
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


def claim_responses_webhook_delivery(
    response_id: str,
    *,
    redis: Any = None,
    redis_url: str = "",
    ttl_seconds: int = DEFAULT_CLAIM_TTL_SECONDS,
) -> bool:
    """True when this replica should deliver. Redis errors fail open."""
    from daari.gateway.request_log import log_gateway_event

    rid = (response_id or "").strip()
    if not rid:
        return True
    client = _redis_client(redis, redis_url)
    if client is None:
        return True
    key = f"{REDIS_KEY_PREFIX}{rid}"
    try:
        claimed = client.set(key, "1", nx=True, ex=int(ttl_seconds))
    except Exception as exc:  # noqa: BLE001 — fail open
        log_gateway_event(
            "responses.completion_webhook_dedupe_degraded",
            {
                "error": f"{type(exc).__name__}: {exc}",
                "id": rid,
            },
        )
        return True
    return bool(claimed)


def deliver_responses_completion_webhook(
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
    """POST a signed completion payload with one retry on 5xx/transport.

    Failures log; never raise. Returns a result label for metrics
    (``ok``, ``error``, or ``skipped``).
    """
    from daari.gateway.request_log import log_gateway_event

    target = (url or "").strip()
    if not target:
        _record_result(metrics, "skipped")
        return "skipped"
    payload = responses_completion_payload(body)
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

            with httpx.Client(transport=transport, timeout=timeout) as client:
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
        "responses.completion_webhook_failed",
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
    return True


def schedule_responses_completion_webhook(
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
        rid = str((body or {}).get("id") or "")
        if not claim_responses_webhook_delivery(
            rid, redis=redis, redis_url=redis_url
        ):
            _record_result(metrics, "deduped")
            return
        deliver_responses_completion_webhook(
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

    thread = threading.Thread(target=_run, daemon=True, name="daari-responses-webhook")
    with _pending_lock:
        _pending.append(thread)
    thread.start()
    return thread


def wait_responses_webhooks(timeout: float = 5.0) -> None:
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
