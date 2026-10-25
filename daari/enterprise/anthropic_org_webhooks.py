"""Ingest Anthropic organization enforcement webhooks (#1875).

Opt-in ``POST /v1/daari/webhooks/anthropic/org`` verifies Standard Webhooks
signatures (``webhook-id`` / ``webhook-timestamp`` / ``webhook-signature``)
with the Anthropic ``whsec_`` signing secret, then updates the local
enforcement cache used by doctor/stats/Prom.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from datetime import datetime, timezone
from typing import Any, Mapping

from daari.enterprise.enforcement_sync import (
    DEFAULT_BASE_URL,
    ENFORCED_STATUSES,
    EnforcementStore,
    _normalize_status,
    _record_from_profile,
    end_users_for_profile,
)

ENFORCEMENT_OPENED = "user_profile.enforcement_action_opened"
ENFORCEMENT_RESOLVED = "user_profile.enforcement_action_resolved"
KNOWN_EVENT_TYPES = frozenset({ENFORCEMENT_OPENED, ENFORCEMENT_RESOLVED})
DEFAULT_REPLAY_TOLERANCE_SECONDS = 300
WEBHOOK_ID_HEADER = "webhook-id"
WEBHOOK_TIMESTAMP_HEADER = "webhook-timestamp"
WEBHOOK_SIGNATURE_HEADER = "webhook-signature"
REDIS_WEBHOOK_DEDUP_PREFIX = "daari:anthropic-org-webhook:"


class OrgWebhookDisabled(Exception):
    """Signing secret not configured — endpoint should 404."""


class OrgWebhookUnauthorized(Exception):
    """Signature verification failed — endpoint should 401."""


def _default_transport() -> Any:
    """Hook point for unit tests (MockTransport)."""
    return None


def _secret_bytes(secret: str) -> bytes:
    text = (secret or "").strip()
    if text.startswith("whsec_"):
        text = text[len("whsec_") :]
    try:
        return base64.b64decode(text)
    except Exception:
        return text.encode("utf-8")


def sign_standard_webhook(
    body: bytes,
    secret: str,
    msg_id: str,
    timestamp: str,
) -> str:
    """Return ``v1,<base64>`` Standard Webhooks signature."""
    key = _secret_bytes(secret)
    to_sign = f"{msg_id}.{timestamp}.".encode("utf-8") + body
    digest = hmac.new(key, to_sign, hashlib.sha256).digest()
    return "v1," + base64.b64encode(digest).decode("ascii")


def _header(headers: Mapping[str, str], name: str) -> str:
    lower = name.lower()
    for key, value in headers.items():
        if key.lower() == lower:
            return str(value or "")
    return ""


def verify_standard_webhook_signature(
    body: bytes,
    headers: Mapping[str, str],
    secret: str,
    *,
    previous_secret: str = "",
    now: int | None = None,
    tolerance_seconds: int = DEFAULT_REPLAY_TOLERANCE_SECONDS,
) -> bool:
    """Verify Anthropic org webhook delivery (Standard Webhooks)."""
    secrets = [s for s in (secret, previous_secret) if (s or "").strip()]
    if not secrets:
        return False
    msg_id = _header(headers, WEBHOOK_ID_HEADER).strip()
    timestamp = _header(headers, WEBHOOK_TIMESTAMP_HEADER).strip()
    signature_header = _header(headers, WEBHOOK_SIGNATURE_HEADER).strip()
    if not msg_id or not timestamp or not signature_header:
        return False
    try:
        ts = int(timestamp)
    except (TypeError, ValueError):
        return False
    moment = int(time.time()) if now is None else int(now)
    if abs(moment - ts) > int(tolerance_seconds):
        return False
    candidates: list[str] = []
    for part in signature_header.split():
        token = part.strip()
        if not token:
            continue
        if token.startswith("v1,"):
            candidates.append(token)
        elif token.startswith("v1="):
            # Tolerate alternate separators some clients emit.
            candidates.append("v1," + token[3:])
    if not candidates:
        return False
    for sec in secrets:
        expected = sign_standard_webhook(body, sec, msg_id, timestamp)
        for cand in candidates:
            if hmac.compare_digest(expected, cand):
                return True
    return False


def fetch_user_profile(
    api_key: str,
    profile_id: str,
    *,
    base_url: str = DEFAULT_BASE_URL,
    transport: Any | None = None,
    timeout: float = 15.0,
) -> dict[str, Any] | None:
    """GET /v1/user_profiles/{id}; None on 404 or missing key."""
    import httpx

    from daari.router.anthropic_messages import ANTHROPIC_VERSION_NO_SAMPLING

    key = (api_key or "").strip()
    pid = (profile_id or "").strip()
    if not key or not pid:
        return None
    root = (base_url or DEFAULT_BASE_URL).rstrip("/")
    if root.endswith("/v1"):
        root = root[:-3].rstrip("/")
    headers = {
        "x-api-key": key,
        "anthropic-version": ANTHROPIC_VERSION_NO_SAMPLING,
        "content-type": "application/json",
    }
    url = f"{root}/v1/user_profiles/{pid}"
    use_transport = transport if transport is not None else _default_transport()
    with httpx.Client(transport=use_transport, timeout=timeout) as client:
        response = client.get(url, headers=headers)
        if response.status_code == 404:
            return None
        response.raise_for_status()
        body = response.json()
        return body if isinstance(body, dict) else None


def _upsert_store(
    store: EnforcementStore,
    *,
    profile_id: str,
    status: str,
    actions: list[Any],
    user_profiles: dict[str, str] | None,
) -> dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()
    row = {
        "profile_id": profile_id,
        "enforcement_status": status,
        "enforcement_actions": actions,
        "end_users": end_users_for_profile(profile_id, user_profiles),
        "updated_at": now,
    }
    rows = [r for r in store.load() if str(r.get("profile_id") or "") != profile_id]
    if status in ENFORCED_STATUSES:
        rows.append(row)
    store.save(rows)
    return row


def _remove_from_store(store: EnforcementStore, profile_id: str) -> dict[str, Any] | None:
    previous = None
    kept: list[dict[str, Any]] = []
    for row in store.load():
        if str(row.get("profile_id") or "") == profile_id:
            previous = row
            continue
        kept.append(row)
    store.save(kept)
    return previous


def _claim_webhook_id(
    webhook_id: str,
    *,
    redis: Any | None,
    ttl_seconds: int = DEFAULT_REPLAY_TOLERANCE_SECONDS,
) -> bool:
    """True when this delivery should be applied. No redis → always claim."""
    from daari.gateway.request_log import log_gateway_event

    wid = (webhook_id or "").strip()
    if not wid or redis is None:
        return True
    key = f"{REDIS_WEBHOOK_DEDUP_PREFIX}{wid}"
    try:
        claimed = redis.set(key, "1", nx=True, ex=int(ttl_seconds))
    except Exception as exc:  # noqa: BLE001 — fail open
        log_gateway_event(
            "anthropic.enforcement_webhook_dedupe_degraded",
            {"error": f"{type(exc).__name__}: {exc}", "webhook_id": wid},
        )
        return True
    return bool(claimed)


def _record_org_webhook_metric(metrics: Any, result: str) -> None:
    if metrics is None or not hasattr(metrics, "record_org_enforcement_webhook"):
        return
    try:
        metrics.record_org_enforcement_webhook(result)
    except Exception:  # noqa: BLE001
        return


def ingest_org_webhook(
    *,
    body: bytes,
    headers: Mapping[str, str],
    signing_secret: str,
    signing_secret_previous: str = "",
    user_profiles: dict[str, str] | None,
    store: EnforcementStore,
    api_key: str = "",
    base_url: str = DEFAULT_BASE_URL,
    transport: Any | None = None,
    redis: Any | None = None,
    audit: Any | None = None,
    metrics: Any | None = None,
) -> dict[str, Any]:
    """Verify + apply one Anthropic org webhook delivery."""
    from daari.gateway.request_log import log_gateway_event

    secret = (signing_secret or "").strip()
    if not secret:
        raise OrgWebhookDisabled("org webhook signing secret not configured")
    if not verify_standard_webhook_signature(
        body,
        headers,
        secret,
        previous_secret=signing_secret_previous,
    ):
        _record_org_webhook_metric(metrics, "unauthorized")
        raise OrgWebhookUnauthorized("invalid webhook signature")

    webhook_id = _header(headers, WEBHOOK_ID_HEADER).strip()
    if not _claim_webhook_id(webhook_id, redis=redis):
        _record_org_webhook_metric(metrics, "duplicate")
        return {"ok": True, "duplicate": True}

    try:
        payload = json.loads(body.decode("utf-8") if isinstance(body, bytes) else body)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        _record_org_webhook_metric(metrics, "unauthorized")
        raise OrgWebhookUnauthorized("invalid webhook payload") from exc
    if not isinstance(payload, dict):
        _record_org_webhook_metric(metrics, "unauthorized")
        raise OrgWebhookUnauthorized("invalid webhook payload")

    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    event_type = str(data.get("type") or "").strip()
    if event_type not in KNOWN_EVENT_TYPES:
        log_gateway_event(
            "anthropic.enforcement_webhook_ignored",
            {"type": event_type or None, "event_id": payload.get("id")},
        )
        _record_org_webhook_metric(metrics, "ignored")
        return {"ok": True, "ignored": True, "type": event_type or None}

    profile_id = str(data.get("id") or "").strip()
    action_id = str(data.get("enforcement_action_id") or "").strip()
    if not profile_id:
        _record_org_webhook_metric(metrics, "ignored")
        return {"ok": True, "ignored": True, "type": event_type, "reason": "missing_profile_id"}

    profile = None
    try:
        profile = fetch_user_profile(
            api_key,
            profile_id,
            base_url=base_url,
            transport=transport if transport is not None else _default_transport(),
        )
    except Exception as exc:
        log_gateway_event(
            "anthropic.enforcement_webhook_profile_fetch_failed",
            {
                "profile_id": profile_id,
                "error": f"{type(exc).__name__}: {exc}",
            },
        )

    previous = {
        str(row["profile_id"]): row
        for row in store.load()
        if _normalize_status(str(row.get("enforcement_status") or "")) in ENFORCED_STATUSES
    }
    was_enforced = profile_id in previous

    if profile is not None:
        status = _normalize_status(str(profile.get("enforcement_status") or ""))
        actions = profile.get("enforcement_actions")
        if not isinstance(actions, list):
            actions = []
        if status in ENFORCED_STATUSES:
            row = _record_from_profile(
                {**profile, "id": profile_id},
                user_profiles=user_profiles,
                updated_at=datetime.now(timezone.utc).isoformat(),
            )
            rows = [r for r in store.load() if str(r.get("profile_id") or "") != profile_id]
            rows.append(row)
            store.save(rows)
        else:
            _remove_from_store(store, profile_id)
            row = {
                "profile_id": profile_id,
                "enforcement_status": status,
                "enforcement_actions": actions,
                "end_users": end_users_for_profile(profile_id, user_profiles),
            }
    else:
        # Best-effort without Admin API: opened → restricted; resolved → clear.
        if event_type == ENFORCEMENT_OPENED:
            status = "restricted"
            actions = [{"id": action_id, "type": "restriction"}] if action_id else []
            row = _upsert_store(
                store,
                profile_id=profile_id,
                status=status,
                actions=actions,
                user_profiles=user_profiles,
            )
        else:
            removed = _remove_from_store(store, profile_id)
            status = "unrestricted"
            row = removed or {
                "profile_id": profile_id,
                "enforcement_status": status,
                "enforcement_actions": [],
                "end_users": end_users_for_profile(profile_id, user_profiles),
            }

    is_enforced = _normalize_status(str(row.get("enforcement_status") or "")) in ENFORCED_STATUSES
    end_users = list(row.get("end_users") or [])

    if is_enforced and not was_enforced:
        log_gateway_event(
            "anthropic.enforcement_started",
            {
                "profile_id": profile_id,
                "enforcement_status": row.get("enforcement_status"),
                "end_users": end_users,
                "enforcement_actions": row.get("enforcement_actions") or [],
                "source": "org_webhook",
            },
        )
    elif was_enforced and not is_enforced:
        log_gateway_event(
            "anthropic.enforcement_ended",
            {
                "profile_id": profile_id,
                "enforcement_status": row.get("enforcement_status"),
                "end_users": end_users,
                "source": "org_webhook",
            },
        )

    log_gateway_event(
        "anthropic.enforcement_webhook_ingested",
        {
            "event_type": event_type,
            "event_id": payload.get("id"),
            "profile_id": profile_id,
            "enforcement_action_id": action_id or None,
            "enforcement_status": row.get("enforcement_status"),
            "end_users": end_users,
        },
    )
    if audit is not None and hasattr(audit, "record"):
        try:
            audit.record(
                actor="anthropic-org-webhook",
                role="system",
                action="anthropic.enforcement_webhook",
                detail={
                    "event_type": event_type,
                    "event_id": payload.get("id"),
                    "webhook_id": webhook_id or None,
                    "profile_id": profile_id,
                    "enforcement_action_id": action_id or None,
                    "enforcement_status": row.get("enforcement_status"),
                    "end_users": end_users,
                },
            )
        except Exception:  # noqa: BLE001 — audit must not break ingest
            pass
    _record_org_webhook_metric(metrics, "ingested")
    return {
        "ok": True,
        "ignored": False,
        "type": event_type,
        "profile_id": profile_id,
        "enforcement_action_id": action_id or None,
        "enforcement_status": row.get("enforcement_status"),
        "end_users": end_users,
    }
