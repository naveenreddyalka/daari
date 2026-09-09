"""OpenRouter `cost_tier` → daari tier cap (#388)."""

from __future__ import annotations

from typing import Any

from daari.gateway.internal import RequestMeta
from daari.gateway.request_log import log_gateway_event

COST_TIER_CAP = {
    "low": "L3",
    "medium": "L4",
    "high": "L5",
    "xhigh": "L6",
    "max": "L6",
}


def extract_cost_tier(body: Any) -> str | None:
    raw = getattr(body, "cost_tier", None)
    if raw is None:
        extra = getattr(body, "model_extra", None) or {}
        if isinstance(extra, dict):
            raw = extra.get("cost_tier")
    if not raw:
        plugins = getattr(body, "plugins", None)
        if plugins is None:
            extra = getattr(body, "model_extra", None) or {}
            if isinstance(extra, dict):
                plugins = extra.get("plugins")
        if isinstance(plugins, list):
            for plugin in plugins:
                if isinstance(plugin, dict) and plugin.get("id") == "auto-router":
                    raw = plugin.get("cost_tier")
                    break
    if raw is None:
        return None
    text = str(raw).strip()
    return text or None


def apply_cost_tier(body: Any, meta: RequestMeta) -> str | None:
    """Fill `meta.tier_cap` from a body `cost_tier` when the header is unset.

    `X-Daari-Tier-Cap` (already on meta) wins. Unknown values are ignored.
    """
    raw = extract_cost_tier(body)
    if raw is None:
        return None
    mapped = COST_TIER_CAP.get(raw.lower())
    if mapped is None:
        log_gateway_event("cost_tier_ignored", {"cost_tier": raw})
        return None
    if (meta.tier_cap or "").strip():
        return mapped
    meta.tier_cap = mapped
    return mapped
