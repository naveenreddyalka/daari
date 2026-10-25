"""Anthropic user-profile enforcement status sync (#1866).

Polls ``GET /v1/user_profiles?enforcement_status[]=restricted&enforcement_status[]=banned``
with the configured frontier key (no ``user-profiles-`` beta header so the
2026-10-21 ``enforcement_*`` fields are present), persists status keyed by
profile id / mapped end user, emits gateway events on transitions, and
optionally POSTs a signed webhook (budget-alert HMAC convention).
"""

from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

from daari.observability.budget_alerts import (
    SIGNATURE_HEADER,
    TIMESTAMP_HEADER,
    signature_header_value,
)
from daari.router.anthropic_messages import ANTHROPIC_VERSION_NO_SAMPLING

DEFAULT_STATE_PATH = Path("~/.daari/anthropic-enforcement.json")
DEFAULT_BASE_URL = "https://api.anthropic.com"
ENFORCED_STATUSES = frozenset({"restricted", "banned"})
_STATE_LOCK = threading.Lock()


def enforcement_state_path(path: str | Path | None = None) -> Path:
    return Path(path or DEFAULT_STATE_PATH).expanduser()


def end_users_for_profile(
    profile_id: str,
    user_profiles: dict[str, str] | None,
) -> list[str]:
    """Local keys (end-user / key_id / team_id / client_id) mapped to ``profile_id``."""
    pid = (profile_id or "").strip()
    if not pid:
        return []
    out: list[str] = []
    for local, mapped in (user_profiles or {}).items():
        if (mapped or "").strip() == pid:
            out.append(str(local))
    return out


def _normalize_status(raw: str | None) -> str:
    status = (raw or "").strip().lower() or "unrestricted"
    if status not in {"unrestricted", "pending", "restricted", "banned"}:
        # Anthropic may add values; treat unknown as restricted.
        return "restricted"
    return status


REDIS_ENFORCEMENT_KEY = "daari:anthropic-enforcement"


@dataclass
class EnforcementStore:
    path: Path
    redis: Any | None = None
    redis_key: str = REDIS_ENFORCEMENT_KEY

    def _load_file(self) -> list[dict[str, Any]]:
        path = Path(self.path)
        if not path.is_file():
            return []
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
        rows = data.get("profiles") if isinstance(data, dict) else data
        if not isinstance(rows, list):
            return []
        return [row for row in rows if isinstance(row, dict) and row.get("profile_id")]

    def load(self) -> list[dict[str, Any]]:
        if self.redis is not None:
            try:
                raw = self.redis.get(self.redis_key)
            except Exception:
                raw = None
            if raw:
                try:
                    text = raw.decode("utf-8") if isinstance(raw, (bytes, bytearray)) else str(raw)
                    data = json.loads(text)
                    rows = data.get("profiles") if isinstance(data, dict) else data
                    if isinstance(rows, list):
                        return [
                            row
                            for row in rows
                            if isinstance(row, dict) and row.get("profile_id")
                        ]
                except (TypeError, json.JSONDecodeError, UnicodeDecodeError):
                    pass
            return []
        return self._load_file()

    def save(self, rows: list[dict[str, Any]]) -> None:
        payload = {
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "profiles": list(rows),
        }
        blob = json.dumps(payload, indent=2) + "\n"
        if self.redis is not None:
            try:
                self.redis.set(self.redis_key, blob)
                return
            except Exception:
                pass
        path = Path(self.path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with _STATE_LOCK:
            path.write_text(blob, encoding="utf-8")

    def enforced_count(self) -> int:
        return sum(
            1
            for row in self.load()
            if _normalize_status(str(row.get("enforcement_status") or ""))
            in ENFORCED_STATUSES
        )


def list_enforced_profiles(
    api_key: str,
    *,
    base_url: str = DEFAULT_BASE_URL,
    transport: Any | None = None,
    timeout: float = 30.0,
) -> list[dict[str, Any]]:
    """List profiles currently restricted or banned via the Anthropic Admin API."""
    import httpx

    key = (api_key or "").strip()
    if not key:
        raise ValueError("Anthropic API key required for enforcement sync")
    root = (base_url or DEFAULT_BASE_URL).rstrip("/")
    if root.endswith("/v1"):
        root = root[:-3].rstrip("/")
    headers = {
        "x-api-key": key,
        "anthropic-version": ANTHROPIC_VERSION_NO_SAMPLING,
        "content-type": "application/json",
    }
    out: list[dict[str, Any]] = []
    page: str | None = None
    with httpx.Client(transport=transport, timeout=timeout) as client:
        while True:
            params: list[tuple[str, str]] = [
                ("enforcement_status[]", "restricted"),
                ("enforcement_status[]", "banned"),
                ("limit", "100"),
            ]
            if page:
                params.append(("page", page))
            url = f"{root}/v1/user_profiles?{urlencode(params)}"
            response = client.get(url, headers=headers)
            response.raise_for_status()
            body = response.json()
            for row in body.get("data") or []:
                if not isinstance(row, dict):
                    continue
                status = _normalize_status(str(row.get("enforcement_status") or ""))
                if status not in ENFORCED_STATUSES:
                    continue
                out.append(row)
            next_page = body.get("next_page")
            if not next_page:
                break
            page = str(next_page)
    return out


@dataclass
class SyncResult:
    enforced_count: int = 0
    started: list[dict[str, Any]] = field(default_factory=list)
    ended: list[dict[str, Any]] = field(default_factory=list)
    unchanged: list[dict[str, Any]] = field(default_factory=list)


def _record_from_profile(
    profile: dict[str, Any],
    *,
    user_profiles: dict[str, str] | None,
    updated_at: str,
) -> dict[str, Any]:
    pid = str(profile.get("id") or "").strip()
    status = _normalize_status(str(profile.get("enforcement_status") or ""))
    actions = profile.get("enforcement_actions")
    if not isinstance(actions, list):
        actions = []
    return {
        "profile_id": pid,
        "enforcement_status": status,
        "enforcement_actions": actions,
        "end_users": end_users_for_profile(pid, user_profiles),
        "updated_at": updated_at,
    }


def _deliver_webhook(
    *,
    webhook_url: str,
    webhook_secret: str,
    webhook_secret_previous: str,
    body: dict[str, Any],
    transport: Any | None,
    timeout: float,
) -> None:
    from daari.gateway.request_log import log_gateway_event

    import httpx

    headers: dict[str, str] = {}
    content: bytes | None = None
    json_body: dict[str, Any] | None = body
    secret = (webhook_secret or "").strip()
    if secret:
        content = json.dumps(body, separators=(",", ":"), sort_keys=True).encode()
        timestamp = str(int(time.time()))
        headers[TIMESTAMP_HEADER] = timestamp
        headers[SIGNATURE_HEADER] = signature_header_value(
            content,
            secret,
            timestamp,
            previous_secret=webhook_secret_previous,
        )
        headers["Content-Type"] = "application/json"
        json_body = None
    try:
        with httpx.Client(transport=transport, timeout=timeout) as client:
            response = client.post(
                webhook_url,
                content=content,
                json=json_body,
                headers=headers or None,
            )
            response.raise_for_status()
    except Exception as exc:
        log_gateway_event(
            "anthropic.enforcement_webhook_failed",
            {"error": f"{type(exc).__name__}: {exc}"},
        )
        return
    log_gateway_event(
        "anthropic.enforcement_webhook",
        {
            "started": len(body.get("started") or []),
            "ended": len(body.get("ended") or []),
        },
    )


def sync_enforcement(
    *,
    api_key: str,
    user_profiles: dict[str, str] | None,
    store: EnforcementStore,
    base_url: str = DEFAULT_BASE_URL,
    transport: Any | None = None,
    timeout: float = 30.0,
    webhook_url: str = "",
    webhook_secret: str = "",
    webhook_secret_previous: str = "",
) -> SyncResult:
    """Fetch enforced profiles, persist, emit start/end events, optional webhook."""
    from daari.gateway.request_log import log_gateway_event

    now = datetime.now(timezone.utc).isoformat()
    previous = {
        str(row["profile_id"]): row
        for row in store.load()
        if _normalize_status(str(row.get("enforcement_status") or "")) in ENFORCED_STATUSES
    }
    fetched = list_enforced_profiles(
        api_key,
        base_url=base_url,
        transport=transport,
        timeout=timeout,
    )
    current_rows = [
        _record_from_profile(row, user_profiles=user_profiles, updated_at=now)
        for row in fetched
        if str(row.get("id") or "").strip()
    ]
    current = {row["profile_id"]: row for row in current_rows}

    started: list[dict[str, Any]] = []
    ended: list[dict[str, Any]] = []
    unchanged: list[dict[str, Any]] = []

    for pid, row in current.items():
        if pid not in previous:
            started.append(row)
            log_gateway_event(
                "anthropic.enforcement_started",
                {
                    "profile_id": pid,
                    "enforcement_status": row["enforcement_status"],
                    "end_users": row["end_users"],
                    "enforcement_actions": row["enforcement_actions"],
                },
            )
        else:
            unchanged.append(row)

    for pid, row in previous.items():
        if pid not in current:
            ended.append(row)
            log_gateway_event(
                "anthropic.enforcement_ended",
                {
                    "profile_id": pid,
                    "enforcement_status": row.get("enforcement_status"),
                    "end_users": row.get("end_users") or [],
                },
            )

    store.save(current_rows)
    result = SyncResult(
        enforced_count=len(current_rows),
        started=started,
        ended=ended,
        unchanged=unchanged,
    )

    url = (webhook_url or "").strip()
    if url and (started or ended):
        _deliver_webhook(
            webhook_url=url,
            webhook_secret=webhook_secret,
            webhook_secret_previous=webhook_secret_previous,
            body={
                "event": "anthropic.enforcement",
                "started": started,
                "ended": ended,
                "enforced_count": result.enforced_count,
            },
            transport=transport,
            timeout=timeout,
        )
    return result


def store_from_settings(settings: Any) -> EnforcementStore:
    anthropic = getattr(settings, "anthropic", None)
    path = getattr(anthropic, "enforcement_state_path", None) if anthropic else None
    redis_client: Any | None = None
    cache = getattr(settings, "cache", None)
    if cache is not None and str(getattr(cache, "backend", "") or "") == "redis":
        url = str(getattr(cache, "redis_url", "") or "").strip()
        if url:
            try:
                from daari.cache.redis_client import connect_redis

                redis_client = connect_redis(
                    url,
                    timeout_seconds=float(getattr(cache, "redis_timeout_seconds", 2.0) or 2.0),
                )
            except Exception:
                redis_client = None
    return EnforcementStore(enforcement_state_path(path), redis=redis_client)
