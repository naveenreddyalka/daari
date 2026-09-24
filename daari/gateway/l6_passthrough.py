"""Shared L6 slot selection + retry for modality passthroughs (#1060)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from daari.gateway.provider_prefs import (
    RegionUnavailable,
    filter_slots_for_region,
    require_region_slot,
)
from daari.router.retry import RETRYABLE_STATUS, RetryPolicy, run_upstream


@dataclass(frozen=True)
class L6Target:
    base_url: str
    api_key: str
    default_model: str
    timeout: float
    slot_id: str = ""
    retry: Any | None = None


def region_pin_from_request(request: Any) -> str | None:
    claims = getattr(getattr(request, "state", None), "auth_claims", None)
    pin = getattr(claims, "region_pin", None) if claims is not None else None
    text = str(pin or "").strip()
    return text or None


def resolve_l6_targets(
    settings: Any,
    *,
    region_pin: str | None,
    default_model: str,
) -> list[L6Target]:
    """Eligible frontier slots in chat order, filtered by region_pin.

    Raises RegionUnavailable when a pin is set but no slot can satisfy it.
    """
    frontier = getattr(settings, "frontier", None)
    if frontier is None or not bool(getattr(frontier, "enabled", False)):
        return []
    from daari.router.frontier_pool import build_frontier_pool
    from daari.router.openrouter import openrouter_base_for_region
    from daari.security.secret_refs import SecretRefError

    pool = build_frontier_pool(settings)
    if not pool.slots:
        return []
    slots = list(pool.slots)
    require_region_slot(region_pin, slots)
    slots = filter_slots_for_region(region_pin, slots)
    targets: list[L6Target] = []
    for slot in slots:
        try:
            key = slot.pick_key()
        except SecretRefError:
            continue
        secret = str(key or "").strip()
        if not secret:
            continue
        slot_base = str(getattr(slot.executor, "base_url", "") or "").strip().rstrip("/")
        if not slot_base:
            continue
        regional = openrouter_base_for_region(region_pin, slot_base).rstrip("/")
        timeout = float(getattr(slot.executor, "timeout", 90.0) or 90.0)
        model = str(getattr(slot.executor, "default_model", "") or "").strip()
        if not model:
            model = str(getattr(frontier, "model", "") or "").strip() or default_model
        retry = getattr(slot, "retry", None)
        if retry is None:
            retry = getattr(getattr(slot, "executor", None), "retry", None)
        targets.append(
            L6Target(
                base_url=regional,
                api_key=secret,
                default_model=model,
                timeout=timeout,
                slot_id=str(getattr(slot, "id", "") or ""),
                retry=retry,
            )
        )
    return targets


async def post_l6(
    client: httpx.AsyncClient,
    url: str,
    *,
    headers: dict[str, str],
    payload: dict[str, Any],
    timeout: float,
    upstream: str,
    retry: Any | None = None,
    metrics: Any | None = None,
) -> httpx.Response:
    """POST via run_upstream so transient failures retry with metrics."""
    policy = (
        retry
        if isinstance(retry, RetryPolicy)
        else (RetryPolicy(attempts=1) if retry is None else RetryPolicy.from_settings(retry))
    )

    async def attempt() -> httpx.Response:
        response = await client.post(url, headers=headers, json=payload, timeout=timeout)
        if response.status_code in RETRYABLE_STATUS:
            response.raise_for_status()
        return response

    return await run_upstream(
        attempt,
        upstream=upstream,
        policy=policy,
        timeout=timeout,
        metrics=metrics,
    )


def is_slot_failure(response: httpx.Response) -> bool:
    """Whether a non-success response should try the next frontier slot."""
    return response.status_code in RETRYABLE_STATUS or response.status_code >= 500


__all__ = [
    "L6Target",
    "RegionUnavailable",
    "is_slot_failure",
    "post_l6",
    "region_pin_from_request",
    "resolve_l6_targets",
]
