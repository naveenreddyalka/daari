"""Periodic signed org-policy refresh (issue #118 deepen).

Fetches org config from `enterprise.policy_sync_url`, verifies HMAC when a
signing secret is set, and applies safe overrides into the running Settings /
Router in memory. Disk write is optional (persist=True).
"""

from __future__ import annotations

from typing import Any

from daari.enterprise.bootstrap import apply_org_config, fetch_org_config, verify_signature


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


def apply_policy_to_runtime(
    settings: Any,
    router: Any,
    config: dict[str, Any],
) -> dict[str, Any]:
    """Apply a safe subset of org config to live settings + router. Returns applied keys."""
    applied: dict[str, Any] = {}
    routing = config.get("routing") or {}
    if isinstance(routing, dict):
        for key in SAFE_ROUTING_KEYS:
            if key not in routing:
                continue
            value = routing[key]
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
        for key in SAFE_FRONTIER_KEYS:
            if key not in frontier:
                continue
            value = frontier[key]
            setattr(settings.frontier, key, value)
            attr = f"frontier_{key}"
            if hasattr(router, attr):
                setattr(router, attr, value)
            if key == "enabled":
                router.frontier_enabled = bool(value)
            applied[f"frontier.{key}"] = value

    cache = config.get("cache") or {}
    if isinstance(cache, dict):
        if "l0_ttl_seconds" in cache:
            settings.cache.l0.ttl_seconds = float(cache["l0_ttl_seconds"])
            applied["cache.l0_ttl_seconds"] = cache["l0_ttl_seconds"]
        if "l1_ttl_seconds" in cache:
            settings.cache.l1.ttl_seconds = float(cache["l1_ttl_seconds"])
            applied["cache.l1_ttl_seconds"] = cache["l1_ttl_seconds"]
        if "l1_similarity_threshold" in cache:
            thr = float(cache["l1_similarity_threshold"])
            settings.cache.l1.similarity_threshold = thr
            router.semantic_cache.similarity_threshold = thr
            applied["cache.l1_similarity_threshold"] = thr

    guardrails = config.get("guardrails")
    if isinstance(guardrails, dict) and hasattr(settings, "guardrails"):
        if "enabled" in guardrails:
            settings.guardrails.enabled = bool(guardrails["enabled"])
            applied["guardrails.enabled"] = guardrails["enabled"]

    return applied


def sync_policy_once(
    settings: Any,
    router: Any | None = None,
    *,
    persist: bool = False,
    insecure: bool = False,
) -> dict[str, Any]:
    """Fetch + verify + apply. Returns a status dict."""
    url = settings.enterprise.policy_sync_url or ""
    if not url:
        return {"ok": False, "reason": "no_policy_sync_url"}
    data, raw, signature = fetch_org_config(
        url, token=settings.enterprise.org_token or ""
    )
    secret = settings.enterprise.config_signing_secret or ""
    if not insecure and secret and not verify_signature(raw, signature, secret):
        return {"ok": False, "reason": "bad_signature"}
    applied: dict[str, Any] = {}
    if router is not None:
        applied = apply_policy_to_runtime(settings, router, data)
    if persist:
        apply_org_config(data, device_id=settings.enterprise.device_id)
        applied["persisted"] = True
    return {"ok": True, "applied": applied}
