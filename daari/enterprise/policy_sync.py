"""Periodic signed org-policy refresh (issue #118 deepen).

Fetches org config from `enterprise.policy_sync_url`, verifies the HMAC
signature, and applies safe overrides into the running Settings / Router in
memory. Disk write is optional (persist=True).

Remote policy can disable guardrails and raise spend budgets, so transport and
signature are both mandatory: HTTPS (or loopback) plus a configured signing
secret. `insecure=True` is the single, explicit opt-out for local testing.
"""

from __future__ import annotations

import hashlib
import json
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from daari.enterprise.bootstrap import (
    PolicySchemaError,
    apply_org_config,
    fetch_org_config,
    validate_policy_schema,
    verify_signature,
)
from daari.gateway.request_log import log_gateway_event


LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1", "[::1]"}
DEFAULT_POLICY_STATE_PATH = Path("~/.daari/policy-sync-state.json")

SAFE_ROUTING_KEYS = {
    "prefer",
    "confidence_threshold",
    "latency_budget_ms",
    "max_tier_for_chat",
}
SAFE_FRONTIER_KEYS = {
    "daily_budget_usd",
    "monthly_budget_usd",
    "soft_budget_ratio",
    "enabled",
}
SAFE_CACHE_KEYS = {
    "l0_ttl_seconds",
    "l1_ttl_seconds",
    "l1_similarity_threshold",
}

_ROUTING_COERCE: dict[str, Any] = {
    "prefer": str,
    "confidence_threshold": float,
    "latency_budget_ms": int,
    "max_tier_for_chat": str,
}

_FRONTIER_COERCE: dict[str, Any] = {
    "daily_budget_usd": float,
    "monthly_budget_usd": float,
    "soft_budget_ratio": float,
    "enabled": bool,
}

_UNSET = object()
_STATE_LOCK = threading.Lock()
_RUNTIME_STATUS: PolicyStatus | None = None


@dataclass
class PolicyStatus:
    """Last successful policy apply (#1138)."""

    policy_hash: str | None = None
    applied_at: str | None = None
    source_url: str | None = None
    configured: bool = False

    @property
    def applied(self) -> bool:
        return bool(self.policy_hash and self.applied_at)


def redact_policy_url(url: str) -> str:
    """Keep scheme + host only (no path/query/token)."""
    parsed = urlparse((url or "").strip())
    if not parsed.scheme or not parsed.hostname:
        return ""
    return f"{parsed.scheme}://{parsed.hostname}"


def policy_content_hash(config: dict[str, Any]) -> str:
    """Stable SHA-256 of the verified policy payload."""
    blob = json.dumps(config, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def policy_state_path(path: str | Path | None = None) -> Path:
    return Path(path or DEFAULT_POLICY_STATE_PATH).expanduser()


def record_policy_apply(
    config: dict[str, Any],
    *,
    url: str = "",
    applied_at: datetime | None = None,
    state_path: str | Path | None = None,
    configured: bool = True,
) -> PolicyStatus:
    """Persist last-applied hash/URL for doctor / policy-status (#1138)."""
    global _RUNTIME_STATUS
    when = applied_at or datetime.now(timezone.utc)
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    status = PolicyStatus(
        policy_hash=policy_content_hash(config),
        applied_at=when.astimezone(timezone.utc).isoformat(),
        source_url=redact_policy_url(url) or None,
        configured=configured,
    )
    path = policy_state_path(state_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "policy_hash": status.policy_hash,
        "applied_at": status.applied_at,
        "source_url": status.source_url,
    }
    with _STATE_LOCK:
        path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        _RUNTIME_STATUS = status
    return status


def load_policy_status(
    *,
    settings: Any | None = None,
    state_path: str | Path | None = None,
) -> PolicyStatus:
    """Return in-memory status if set, else disk, else never-applied."""
    configured = False
    if settings is not None:
        configured = bool(getattr(settings.enterprise, "policy_sync_url", None) or "")
    with _STATE_LOCK:
        if _RUNTIME_STATUS is not None:
            return PolicyStatus(
                policy_hash=_RUNTIME_STATUS.policy_hash,
                applied_at=_RUNTIME_STATUS.applied_at,
                source_url=_RUNTIME_STATUS.source_url,
                configured=configured or _RUNTIME_STATUS.configured,
            )
    path = policy_state_path(state_path)
    if path.is_file():
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            raw = {}
        if isinstance(raw, dict) and raw.get("policy_hash"):
            return PolicyStatus(
                policy_hash=str(raw.get("policy_hash") or "") or None,
                applied_at=str(raw.get("applied_at") or "") or None,
                source_url=str(raw.get("source_url") or "") or None,
                configured=configured,
            )
    return PolicyStatus(configured=configured)


def clear_policy_status_for_tests() -> None:
    """Reset module runtime state between unit tests."""
    global _RUNTIME_STATUS
    with _STATE_LOCK:
        _RUNTIME_STATUS = None


def _coerce(value: Any, caster: Any, *, section: str, key: str) -> Any:
    """Cast a remote value, or return _UNSET so one bad field can't abort the sync."""
    try:
        return caster(value)
    except (TypeError, ValueError):
        log_gateway_event(
            "policy_sync_value_rejected",
            {"section": section, "key": key, "value": repr(value)[:120]},
        )
        return _UNSET


def policy_url_is_secure(url: str) -> bool:
    """HTTPS everywhere; plaintext only to loopback for local testing."""
    parsed = urlparse(url)
    if parsed.scheme == "https":
        return True
    if parsed.scheme == "http":
        return (parsed.hostname or "") in LOOPBACK_HOSTS
    return False


def apply_policy_to_runtime(
    settings: Any,
    router: Any,
    config: dict[str, Any],
    *,
    source_url: str = "",
    state_path: str | Path | None = None,
    record: bool = False,
) -> dict[str, Any]:
    """Apply a safe subset of org config to live settings + router. Returns applied keys."""
    validate_policy_schema(config)
    applied: dict[str, Any] = {}
    routing = config.get("routing") or {}
    if isinstance(routing, dict):
        for key in sorted(SAFE_ROUTING_KEYS):
            if key not in routing:
                continue
            value = _coerce(routing[key], _ROUTING_COERCE[key], section="routing", key=key)
            if value is _UNSET:
                continue
            setattr(settings.routing, key, value)
            if key == "confidence_threshold":
                router.confidence_threshold = float(value)
            elif key == "latency_budget_ms":
                router.latency_budget_ms = int(value)
            elif key == "max_tier_for_chat":
                router.max_tier_for_chat = value
            elif key == "prefer":
                router.model_preference = str(value)
            applied[f"routing.{key}"] = value

    frontier = config.get("frontier") or {}
    if isinstance(frontier, dict):
        for key in sorted(SAFE_FRONTIER_KEYS):
            if key not in frontier:
                continue
            value = _coerce(frontier[key], _FRONTIER_COERCE[key], section="frontier", key=key)
            if value is _UNSET:
                continue
            setattr(settings.frontier, key, value)
            attr = f"frontier_{key}"
            if hasattr(router, attr):
                setattr(router, attr, value)
            if key == "enabled":
                router.frontier_enabled = bool(value)
            applied[f"frontier.{key}"] = value

    cache = config.get("cache") or {}
    if isinstance(cache, dict):
        for key in sorted(SAFE_CACHE_KEYS):
            if key not in cache:
                continue
            value = _coerce(cache[key], float, section="cache", key=key)
            if value is _UNSET:
                continue
            if key == "l0_ttl_seconds":
                settings.cache.l0.ttl_seconds = value
            elif key == "l1_ttl_seconds":
                settings.cache.l1.ttl_seconds = value
            else:
                settings.cache.l1.similarity_threshold = value
                router.semantic_cache.similarity_threshold = value
            applied[f"cache.{key}"] = value

    guardrails = config.get("guardrails")
    if isinstance(guardrails, dict) and hasattr(settings, "guardrails"):
        if "enabled" in guardrails:
            settings.guardrails.enabled = bool(guardrails["enabled"])
            applied["guardrails.enabled"] = guardrails["enabled"]

    boundaries = config.get("boundaries")
    if isinstance(boundaries, dict) and hasattr(settings, "boundaries"):
        from daari.config.validate import ConfigValidationError, merged_boundaries

        known = {k: v for k, v in boundaries.items() if hasattr(settings.boundaries, k)}
        try:
            settings.boundaries = merged_boundaries(settings.boundaries, known)
        except ConfigValidationError as exc:
            log_gateway_event(
                "policy_sync_value_rejected",
                {"section": "boundaries", "error": str(exc)},
            )
            known = {}
        for key, value in known.items():
            applied[f"boundaries.{key}"] = value
        if known and router is not None:
            from daari.gateway.boundaries import (
                copy_runtime_hooks,
                default_local_judge,
                engine_from_settings,
            )

            prev = router.boundaries
            router.boundaries = engine_from_settings(settings, judge=default_local_judge)
            copy_runtime_hooks(router.boundaries, prev)

    if record:
        url = (
            source_url
            or getattr(getattr(settings, "enterprise", None), "policy_sync_url", "")
            or ""
        )
        record_policy_apply(
            config,
            url=str(url),
            state_path=state_path,
            configured=bool(url),
        )
    return applied


def sync_policy_once(
    settings: Any,
    router: Any | None = None,
    *,
    persist: bool = False,
    insecure: bool = False,
    state_path: str | Path | None = None,
) -> dict[str, Any]:
    """Fetch + verify + apply. Returns a status dict."""
    url = settings.enterprise.policy_sync_url or ""
    if not url:
        return {"ok": False, "reason": "no_policy_sync_url"}
    secret = settings.enterprise.config_signing_secret or ""
    if not insecure:
        if not policy_url_is_secure(url):
            return {"ok": False, "reason": "insecure_url"}
        if not secret:
            return {"ok": False, "reason": "no_signing_secret"}
    data, raw, signature = fetch_org_config(url, token=settings.enterprise.org_token or "")
    if not insecure and not verify_signature(raw, signature, secret):
        return {"ok": False, "reason": "bad_signature"}
    try:
        validate_policy_schema(data)
    except PolicySchemaError as exc:
        log_gateway_event("policy_sync_schema_rejected", {"error": str(exc)})
        return {"ok": False, "reason": "unknown_schema", "error": str(exc)}
    applied: dict[str, Any] = {}
    if router is not None:
        applied = apply_policy_to_runtime(
            settings,
            router,
            data,
            source_url=url,
            state_path=state_path,
            record=True,
        )
    else:
        record_policy_apply(data, url=url, state_path=state_path, configured=True)
    if persist:
        apply_org_config(data, device_id=settings.enterprise.device_id)
        applied["persisted"] = True
    status = load_policy_status(settings=settings, state_path=state_path)
    return {
        "ok": True,
        "applied": applied,
        "policy_hash": status.policy_hash,
        "applied_at": status.applied_at,
        "source_url": status.source_url,
    }
