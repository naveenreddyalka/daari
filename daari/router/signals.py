"""Request-fact signals for daari_meta + opt-in signal_overrides (#1996).

Cheap derivations of data the router already has — no model calls.
"""

from __future__ import annotations

from typing import Any

from daari.gateway.agent_ua import sniff_agent_client_id
from daari.gateway.internal import InternalRequest
from daari.router.profile import PromptProfile

SIGNAL_KEYS = frozenset(
    {
        "has_images",
        "has_tools",
        "tool_count",
        "approx_context_tokens",
        "client_agent",
        "category",
        "complexity",
        "phase",
    }
)

_TIER_SET = frozenset({"L3", "L4", "L5"})


def context_token_bucket(tokens: int) -> str:
    """Bucket estimated prompt tokens for equality match (no continuous ranges)."""
    n = max(0, int(tokens))
    if n < 1000:
        return "lt_1k"
    if n < 4000:
        return "1k_4k"
    if n < 16000:
        return "4k_16k"
    return "gte_16k"


def _client_agent_family(request: InternalRequest) -> str:
    ua = getattr(request.meta, "user_agent", None) or ""
    sniffed = sniff_agent_client_id(ua)
    if sniffed:
        return sniffed
    client_id = (getattr(request.meta, "client_id", None) or "").strip().lower()
    if client_id in {"cursor", "claude-code", "codex"}:
        return client_id
    if client_id:
        return "other"
    return "none"


def extract_signals(
    request: InternalRequest,
    profile: PromptProfile,
    *,
    phase: str | None = None,
) -> dict[str, Any]:
    """Bounded fact set for daari_meta / request log / signal_overrides."""
    has_images = any(bool(getattr(m, "images", None)) for m in request.messages)
    tools = list(request.tools or [])
    tool_count = len(tools)
    return {
        "has_images": has_images,
        "has_tools": tool_count > 0 or bool(request.has_tool_calls_in_history),
        "tool_count": tool_count,
        "approx_context_tokens": context_token_bucket(profile.prompt_tokens_est),
        "client_agent": _client_agent_family(request),
        "category": profile.category,
        "complexity": profile.complexity,
        "phase": phase,
    }


def _match_value(actual: Any, expected: Any) -> bool:
    if expected is None:
        return actual is None
    if isinstance(expected, bool):
        return bool(actual) is expected
    return actual == expected


def match_signal_override(signals: dict[str, Any], rules: list[Any]) -> Any | None:
    """First rule whose match dict is fully satisfied; None if none match."""
    for rule in rules or []:
        match = getattr(rule, "match", None)
        if match is None and isinstance(rule, dict):
            match = rule.get("match")
        if not isinstance(match, dict) or not match:
            continue
        if all(_match_value(signals.get(key), expected) for key, expected in match.items()):
            return rule
    return None


def apply_signal_override(
    profile: PromptProfile,
    request: InternalRequest,
    rule: Any,
) -> tuple[PromptProfile, dict[str, str | None]]:
    """Apply category / max_tier / tier_pin levers; mutate request.meta when set."""
    category = getattr(rule, "category", None)
    if category is None and isinstance(rule, dict):
        category = rule.get("category")
    max_tier = getattr(rule, "max_tier", None)
    if max_tier is None and isinstance(rule, dict):
        max_tier = rule.get("max_tier")
    tier_pin = getattr(rule, "tier_pin", None)
    if tier_pin is None and isinstance(rule, dict):
        tier_pin = rule.get("tier_pin")

    new_profile = profile
    if category:
        new_profile = profile.model_copy(update={"category": str(category)})

    max_tier_s = str(max_tier).upper() if max_tier else None
    tier_pin_s = str(tier_pin).upper() if tier_pin else None
    if max_tier_s in _TIER_SET and not request.meta.tier_cap:
        request.meta.tier_cap = max_tier_s
    if tier_pin_s in _TIER_SET and not request.meta.tier_override:
        request.meta.tier_override = tier_pin_s

    return new_profile, {
        "max_tier": max_tier_s if max_tier_s in _TIER_SET else None,
        "tier_pin": tier_pin_s if tier_pin_s in _TIER_SET else None,
    }
