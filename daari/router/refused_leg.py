"""Detect billed safeguard refusals and merge their spend into the serving attempt (#2272)."""

from __future__ import annotations

from daari.gateway.internal import InternalResponse

# OpenAI content_filter + Anthropic/OpenAI refusal stop tokens the router may fall back from.
SAFEGUARD_FINISH_REASONS = frozenset({"refusal", "content_filter"})


def is_safeguard_refusal(response: InternalResponse) -> bool:
    """True when upstream completed a billed safeguard / refusal stop."""
    token = (response.finish_reason or "").strip().lower()
    return token in SAFEGUARD_FINISH_REASONS


def attempt_cost_usd(response: InternalResponse) -> float:
    """USD owed for one completed attempt (local / non-L6 legs are always 0)."""
    meta = response.daari_meta
    tier = (meta.tier or "").upper()
    if tier != "L6" and (meta.executor or "") != "frontier":
        return 0.0
    if meta.cost_usd is not None:
        return max(0.0, float(meta.cost_usd))
    return 0.0


def merge_prior_attempt_cost(serving: InternalResponse, prior_cost_usd: float) -> None:
    """Add a discarded attempt's billed cost onto the response that serves the client."""
    owed = max(0.0, float(prior_cost_usd or 0.0))
    if owed <= 0.0:
        return
    current = serving.daari_meta.cost_usd
    if current is None:
        serving.daari_meta.cost_usd = owed
    else:
        serving.daari_meta.cost_usd = float(current) + owed
