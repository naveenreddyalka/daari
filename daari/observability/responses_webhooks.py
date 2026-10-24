"""Signed completion webhooks for background Responses jobs (#1892).

Reuses ``sign_webhook`` / ``signature_header_value`` from budget alerts.
Empty URL soft-fails with no network call.
"""

from __future__ import annotations

import json
import time
from typing import Any

from daari.observability.budget_alerts import (
    SIGNATURE_HEADER,
    TIMESTAMP_HEADER,
    signature_header_value,
)


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


def deliver_responses_completion_webhook(
    *,
    url: str,
    secret: str = "",
    body: dict[str, Any],
    transport: Any = None,
    timeout: float = 5.0,
) -> None:
    """POST a signed completion payload. Failures log; never raise."""
    from daari.gateway.request_log import log_gateway_event

    target = (url or "").strip()
    if not target:
        return
    payload = responses_completion_payload(body)
    content = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    headers: dict[str, str] = {"Content-Type": "application/json"}
    sec = (secret or "").strip()
    if sec:
        timestamp = str(int(time.time()))
        headers[TIMESTAMP_HEADER] = timestamp
        headers[SIGNATURE_HEADER] = signature_header_value(content, sec, timestamp)
    try:
        import httpx

        with httpx.Client(transport=transport, timeout=timeout) as client:
            response = client.post(target, content=content, headers=headers)
            response.raise_for_status()
    except Exception as exc:  # noqa: BLE001 — best-effort notify
        log_gateway_event(
            "responses.completion_webhook_failed",
            {
                "error": f"{type(exc).__name__}: {exc}",
                "id": payload.get("id"),
                "status": payload.get("status"),
            },
        )
