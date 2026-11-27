"""Shared L6 slot selection + retry for modality passthroughs (#1060)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx
from fastapi.responses import JSONResponse

from daari.auth.frontier_binding import (
    FrontierBindingError,
    effective_binding,
    resolve_bound_key,
)
from daari.gateway.provider_prefs import (
    RegionUnavailable,
    filter_slots_for_region,
    require_region_slot,
)
from daari.router.retry import RETRYABLE_STATUS, RetryPolicy, is_retryable_status, run_upstream


@dataclass(frozen=True)
class L6Target:
    base_url: str
    api_key: str
    default_model: str
    timeout: float
    slot_id: str = ""
    retry: Any | None = None


@dataclass(frozen=True)
class FrontierBinding:
    """Team/key BYOK binding for an L6 door (#2216, #2313). Empty = global key."""

    api_key: str | None = None
    pool: str | None = None

    def __bool__(self) -> bool:
        return bool(self.api_key or self.pool)


def region_pin_from_request(request: Any) -> str | None:
    claims = getattr(getattr(request, "state", None), "auth_claims", None)
    pin = getattr(claims, "region_pin", None) if claims is not None else None
    text = str(pin or "").strip()
    return text or None


def frontier_binding_from_request(request: Any) -> FrontierBinding:
    """Same key-over-team precedence as ``apply_auth_claims_to_meta`` on chat."""
    claims = getattr(getattr(request, "state", None), "auth_claims", None)
    if claims is None:
        return FrontierBinding()
    vk = getattr(claims, "virtual_key", None)
    api_key, pool = effective_binding(
        key_api_key=getattr(vk, "frontier_api_key", None) if vk is not None else None,
        key_pool=getattr(vk, "frontier_pool", None) if vk is not None else None,
        team_api_key=getattr(claims, "team_frontier_api_key", None),
        team_pool=getattr(claims, "team_frontier_pool", None),
    )
    api_text = str(api_key or "").strip() or None
    pool_text = str(pool or "").strip() or None
    return FrontierBinding(api_key=api_text, pool=pool_text)


def frontier_binding_error_response(exc: FrontierBindingError) -> JSONResponse:
    """Fail closed: bound credential problems never fall back to the global key."""
    return JSONResponse(
        status_code=int(getattr(exc, "status_code", 502) or 502),
        content={"error": {"type": "frontier_binding_error", "message": str(exc)}},
    )


def resolve_l6_targets(
    settings: Any,
    *,
    region_pin: str | None,
    default_model: str,
    binding: FrontierBinding | None = None,
) -> list[L6Target]:
    """Eligible frontier slots in chat order, filtered by region_pin and binding.

    Raises RegionUnavailable when a pin is set but no slot can satisfy it, and
    FrontierBindingError when a bound ``pool`` names no slot or a bound
    ``api_key`` cannot be resolved (mirrors ``FrontierPool._slots_for_request``
    / ``_key_for_slot`` on the chat leg).
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
    bound = binding or FrontierBinding()
    if bound.pool:
        wanted = str(bound.pool).strip()
        slots = [slot for slot in slots if slot.id == wanted]
        if not slots:
            raise FrontierBindingError(
                f"frontier_pool {wanted!r} is not a configured provider slot",
                status_code=502,
            )
    bound_key = resolve_bound_key(bound.api_key) if bound.api_key else None
    targets: list[L6Target] = []
    for slot in slots:
        if bound_key is not None:
            key = bound_key
        else:
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
        if is_retryable_status(
            response.status_code, failover_on_http_5xx=policy.failover_on_http_5xx
        ):
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
    "FrontierBinding",
    "FrontierBindingError",
    "L6Target",
    "RegionUnavailable",
    "frontier_binding_error_response",
    "frontier_binding_from_request",
    "is_slot_failure",
    "post_l6",
    "region_pin_from_request",
    "resolve_l6_targets",
]
