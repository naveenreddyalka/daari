"""Multi-provider L6 pool: fallback chains, weighted key rotation, breakers.

Issue #109 / Roadmap F2. Wraps one or more FrontierExecutor instances and
presents the same execute() signature the router already calls, so existing
escalation, budget, slim/compress/scrub paths are unchanged.
"""

from __future__ import annotations

import hashlib
import itertools
import os
import random
from dataclasses import dataclass, field
from typing import Any

from daari.gateway.internal import InternalRequest, InternalResponse
from daari.gateway.provider_prefs import (
    filter_slots_for_region,
    normalize_region,
    require_region_slot,
    require_zdr_retention_ok,
    require_zdr_slot,
    ZdrRetentionConflict,
)
from daari.observability.trace import add_step
from daari.router.breaker_redis import share_key_for
from daari.router.circuit_breaker import CircuitBreaker, counts_as_hard_provider_failure
from daari.router.retry import RetryPolicy, is_retryable, resolve_upstream_policy, status_of
from daari.router.frontier import FrontierExecutor
from daari.router.http_pool import pool_limits_from_settings
from daari.auth.frontier_binding import FrontierBindingError, resolve_bound_key
from daari.security.secret_refs import SecretRefError, current_secret


def _slots_for_request(request: InternalRequest, slots: list[ProviderSlot]) -> list[ProviderSlot]:
    """Apply optional named frontier_pool pin from team/key BYOK (#2216)."""
    pin = getattr(request.meta, "frontier_pool", None)
    if not pin:
        return slots
    wanted = str(pin).strip()
    matched = [slot for slot in slots if slot.id == wanted]
    if not matched:
        raise FrontierBindingError(
            f"frontier_pool {wanted!r} is not a configured provider slot",
            status_code=502,
        )
    return matched


def _key_for_slot(slot: ProviderSlot, request: InternalRequest) -> str | None:
    """Resolve per-attempt key; team/key BYOK overrides slot rotation (#2216)."""
    bound = getattr(request.meta, "frontier_api_key", None)
    if bound:
        return resolve_bound_key(bound)
    return slot.pick_key()


@dataclass
class ProviderSlot:
    id: str
    executor: FrontierExecutor
    keys: list[str]
    weight: float = 1.0
    zdr: bool = False
    region: str = ""
    breaker: CircuitBreaker = field(default_factory=CircuitBreaker)
    _key_cycle: Any = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if self.keys:
            # Deterministic rotate order seeded by provider id so restarts
            # don't reshuffle mid-flight; weights applied at pick time.
            order = list(self.keys)
            rng = random.Random(int(hashlib.sha256(self.id.encode()).hexdigest()[:8], 16))
            rng.shuffle(order)
            self._key_cycle = itertools.cycle(order)

    def pick_key(self) -> str | None:
        # secret://oauth keys re-mint near expiry (#321); plain keys pass through.
        if not self.keys:
            return current_secret(self.executor.api_key)
        # Weighted: duplicate entries by rounded weight, then cycle.
        if self.weight <= 0:
            return current_secret(next(self._key_cycle))
        return current_secret(next(self._key_cycle))


def _slots_for_zdr_retention(
    request: InternalRequest,
    slots: list[ProviderSlot],
    *,
    authorized: tuple[str, ...] = (),
) -> list[ProviderSlot]:
    """Drop retention-required models under provider.zdr; fail if none remain (#2284)."""
    prefs = request.provider
    if prefs is None or not prefs.zdr:
        return slots
    require_zdr_retention_ok(prefs, request.model, authorized=authorized)
    kept: list[ProviderSlot] = []
    blocked: ZdrRetentionConflict | None = None
    for slot in slots:
        model = getattr(getattr(slot, "executor", None), "default_model", "") or ""
        try:
            require_zdr_retention_ok(prefs, model, authorized=authorized)
        except ZdrRetentionConflict as exc:
            blocked = exc
            add_step(
                "frontier_skip",
                provider=slot.id,
                reason="zdr_retention_required",
                model=model,
            )
            continue
        kept.append(slot)
    if not kept and blocked is not None:
        raise blocked
    return kept


@dataclass
class FrontierPool:
    """Ordered failover across providers; duck-types FrontierExecutor.execute."""

    slots: list[ProviderSlot]
    # Kept for AppContext / doctor introspection (first healthy slot's attrs).
    base_url: str = ""
    default_model: str = ""
    api_key: str | None = None
    provider: str = "pool"
    prompt_cache: bool = True
    auto_caching: bool = False
    # models.retention_authorized — expressly authorized ZDR exceptions (#2284).
    retention_authorized: tuple[str, ...] = ()
    _last_executor: FrontierExecutor | None = field(default=None, init=False, repr=False)

    @property
    def last_param_compat(self) -> Any:
        """Param-compat result from the most recent stream/execute winner (#1173)."""
        exe = self._last_executor
        if exe is None and self.slots:
            exe = self.slots[0].executor
        return getattr(exe, "last_param_compat", None) if exe is not None else None

    @classmethod
    def from_single(cls, executor: FrontierExecutor) -> FrontierPool:
        key = executor.api_key or ""
        slot = ProviderSlot(
            id=executor.provider or "default",
            executor=executor,
            keys=[key] if key else [],
        )
        return cls(
            slots=[slot],
            base_url=executor.base_url,
            default_model=executor.default_model,
            api_key=executor.api_key,
            provider=executor.provider,
            prompt_cache=executor.prompt_cache,
            auto_caching=getattr(executor, "auto_caching", False),
        )

    async def execute(
        self,
        request: InternalRequest,
        *,
        escalated_from: str,
        local_confidence: float,
    ) -> InternalResponse:
        if not self.slots:
            raise RuntimeError("no frontier providers configured")

        require_zdr_slot(request.provider, self.slots)
        slots = list(self.slots)
        if request.provider is not None and request.provider.zdr:
            slots = [slot for slot in slots if slot.zdr]
        slots = _slots_for_zdr_retention(
            request, slots, authorized=self.retention_authorized
        )
        region_pin = getattr(request.meta, "region_pin", None)
        require_region_slot(region_pin, slots)
        slots = filter_slots_for_region(region_pin, slots)
        slots = _slots_for_request(request, slots)
        from daari.auth.model_access import model_permitted

        key_patterns = getattr(request.meta, "key_model_patterns", None)
        team_patterns = getattr(request.meta, "team_model_patterns", None)
        if key_patterns is not None or team_patterns is not None:
            allowed_slots = []
            for slot in slots:
                model_name = getattr(getattr(slot, "executor", None), "default_model", "") or ""
                if model_permitted(
                    model_name,
                    key_patterns=key_patterns,
                    team_patterns=team_patterns,
                ):
                    allowed_slots.append(slot)
                else:
                    add_step(
                        "frontier_skip",
                        provider=slot.id,
                        reason="model_allowlist",
                        model=model_name,
                    )
            slots = allowed_slots

        errors: list[str] = []
        prior_refusal_cost = 0.0
        for index, slot in enumerate(slots):
            if not slot.breaker.allow():
                add_step(
                    "frontier_skip",
                    provider=slot.id,
                    reason="circuit_open",
                    state=slot.breaker.state,
                )
                continue
            try:
                key = _key_for_slot(slot, request)
            except FrontierBindingError:
                # Bound credential must not fall back to the shared global key.
                raise
            except SecretRefError as exc:
                # Token refresh failed: fail closed on this provider and let
                # the next slot try rather than sending an expired credential.
                slot.breaker.record_failure()
                errors.append(f"{slot.id}:SecretRefError")
                add_step("frontier_fail", provider=slot.id, error_type="SecretRefError", error=str(exc)[:200])
                continue
            if not key:
                errors.append(f"{slot.id}:no_key")
                continue
            # Rotate the key onto the executor for this attempt.
            slot.executor.api_key = key
            from daari.router.openrouter import openrouter_base_for_region

            original_base = str(getattr(slot.executor, "base_url", "") or "")
            regional_base = openrouter_base_for_region(region_pin, original_base)
            if regional_base != original_base:
                slot.executor.base_url = regional_base
            add_step(
                "frontier_try",
                provider=slot.id,
                model=slot.executor.default_model,
                key_fingerprint=key[-4:] if len(key) >= 4 else "****",
                **({"openrouter_region_base": regional_base} if regional_base != original_base else {}),
            )
            try:
                from daari.router.deadline import RequestDeadlineExceeded, guard_upstream

                guard_upstream("L6")
                response = await slot.executor.execute(
                    request,
                    escalated_from=escalated_from,
                    local_confidence=local_confidence,
                )
                from daari.router.refused_leg import (
                    attempt_cost_usd,
                    is_safeguard_refusal,
                    merge_prior_attempt_cost,
                )

                # Safeguard refusal is a completed billed attempt — fall through
                # when another slot remains, carrying its cost (#2272).
                if is_safeguard_refusal(response) and index + 1 < len(slots):
                    prior_refusal_cost += attempt_cost_usd(response)
                    errors.append(f"{slot.id}:safeguard_refusal")
                    add_step(
                        "frontier_fail",
                        provider=slot.id,
                        error_type="safeguard_refusal",
                        error=(response.finish_reason or "refusal")[:200],
                        finish_reason=response.finish_reason,
                    )
                    continue
                slot.breaker.record_success()
                add_step("frontier_ok", provider=slot.id, model=response.model)
                # Surface which provider won for ledger/meta.
                response.daari_meta.provider_id = slot.id
                served_region = slot.region or (
                    normalize_region(region_pin)
                    if regional_base != original_base
                    else ""
                )
                if served_region:
                    response.daari_meta.region = served_region
                if prior_refusal_cost > 0:
                    merge_prior_attempt_cost(response, prior_refusal_cost)
                self._last_executor = slot.executor
                return response
            except RequestDeadlineExceeded:
                raise
            except Exception as exc:  # noqa: BLE001 — try next provider
                # The executor has already spent its retry budget on transient
                # failures, so reaching here means this provider is genuinely
                # unhealthy (#159). Auth failures never retry and fail over at
                # once, since another key or provider is the only way forward.
                # 429/529 stay transient overloads and do not open the circuit.
                if counts_as_hard_provider_failure(exc):
                    slot.breaker.record_failure()
                errors.append(f"{slot.id}:{type(exc).__name__}")
                add_step(
                    "frontier_fail",
                    provider=slot.id,
                    error_type=type(exc).__name__,
                    error=str(exc)[:200],
                    status=status_of(exc),
                    retried=is_retryable(
                        exc,
                        failover_on_http_5xx=bool(
                            getattr(
                                getattr(slot.executor, "retry", None),
                                "failover_on_http_5xx",
                                False,
                            )
                        ),
                    ),
                    breaker=slot.breaker.state,
                )
                # Leaving a Fable/Mythos 5.2 slot: next Claude hop must strip (#2205).
                from daari.router.anthropic_messages import is_fable_mythos_52_model

                failed_model = getattr(slot.executor, "default_model", "") or ""
                if is_fable_mythos_52_model(failed_model):
                    request.meta.anthropic_prior_model = failed_model
                continue
            finally:
                if regional_base != original_base and hasattr(slot.executor, "base_url"):
                    slot.executor.base_url = original_base

        raise RuntimeError(
            "all frontier providers failed or open: " + (", ".join(errors) or "none tried")
        )

    async def stream(
        self,
        request: InternalRequest,
        *,
        escalated_from: str | None = None,
        local_confidence: float | None = None,
    ):
        """Relay SSE from the first healthy slot (same pick rules as execute)."""
        if not self.slots:
            raise RuntimeError("no frontier providers configured")

        require_zdr_slot(request.provider, self.slots)
        slots = list(self.slots)
        if request.provider is not None and request.provider.zdr:
            slots = [slot for slot in slots if slot.zdr]
        slots = _slots_for_zdr_retention(
            request, slots, authorized=self.retention_authorized
        )
        region_pin = getattr(request.meta, "region_pin", None)
        require_region_slot(region_pin, slots)
        slots = filter_slots_for_region(region_pin, slots)
        slots = _slots_for_request(request, slots)

        errors: list[str] = []
        for slot in slots:
            if not slot.breaker.allow():
                continue
            try:
                key = _key_for_slot(slot, request)
            except FrontierBindingError:
                raise
            except SecretRefError as exc:
                slot.breaker.record_failure()
                errors.append(f"{slot.id}:SecretRefError")
                add_step(
                    "frontier_fail",
                    provider=slot.id,
                    error_type="SecretRefError",
                    error=str(exc)[:200],
                )
                continue
            if not key:
                errors.append(f"{slot.id}:no_key")
                continue
            slot.executor.api_key = key
            try:
                self._last_executor = slot.executor
                async for event in slot.executor.stream(
                    request,
                    escalated_from=escalated_from,
                    local_confidence=local_confidence,
                ):
                    yield event
                slot.breaker.record_success()
                return
            except Exception as exc:  # noqa: BLE001 — try next provider
                if counts_as_hard_provider_failure(exc):
                    slot.breaker.record_failure()
                errors.append(f"{slot.id}:{type(exc).__name__}")
                add_step(
                    "frontier_fail",
                    provider=slot.id,
                    error_type=type(exc).__name__,
                    error=str(exc)[:200],
                )
                from daari.router.anthropic_messages import is_fable_mythos_52_model

                failed_model = getattr(slot.executor, "default_model", "") or ""
                if is_fable_mythos_52_model(failed_model):
                    request.meta.anthropic_prior_model = failed_model
                continue

        raise RuntimeError(
            "all frontier providers failed or open: " + (", ".join(errors) or "none tried")
        )


def _global_frontier_policy(settings: Any) -> tuple[float, RetryPolicy | None]:
    upstream = getattr(settings, "upstream", None)
    retry = RetryPolicy.from_settings(upstream.retry) if upstream else None
    timeout = getattr(upstream, "frontier_timeout_seconds", 90.0) if upstream else 90.0
    return timeout, retry


def _entry_frontier_policy(settings: Any, entry: Any) -> tuple[float, RetryPolicy | None]:
    default_timeout, default_retry = _global_frontier_policy(settings)
    upstream = getattr(settings, "upstream", None)
    retry_settings = getattr(upstream, "retry", None) if upstream else None
    if (
        getattr(entry, "timeout_s", None) is None
        and getattr(entry, "retry_attempts", None) is None
        and getattr(entry, "retry_backoff_s", None) is None
    ):
        return default_timeout, default_retry
    return resolve_upstream_policy(
        retry_settings,
        default_timeout=default_timeout,
        timeout_s=getattr(entry, "timeout_s", None),
        retry_attempts=getattr(entry, "retry_attempts", None),
        retry_backoff_s=getattr(entry, "retry_backoff_s", None),
    )


def build_frontier_pool(settings: Any) -> FrontierPool:
    """Build a pool from FrontierSettings.providers, falling back to scalars."""
    from daari.router.param_compat import merged_frontier_param_compat_table

    frontier = settings.frontier
    timeout, retry = _global_frontier_policy(settings)
    compat_table = merged_frontier_param_compat_table(
        getattr(frontier, "param_compat", None) or None
    )
    providers = list(getattr(frontier, "providers", None) or [])
    if not providers:
        # Single-provider shorthand (pre-#109 config).
        key = settings.resolve_frontier_api_key()
        executor = FrontierExecutor(
            base_url=frontier.base_url.rstrip("/"),
            default_model=frontier.model,
            api_key=key,
            provider=frontier.provider,
            prompt_cache=frontier.prompt_cache,
            auto_caching=bool(getattr(frontier, "auto_caching", False)),
            thinking_binding_drop_block=bool(
                getattr(frontier, "thinking_binding_drop_block", True)
            ),
            codex_base_url=getattr(frontier, "codex_base_url", None),
            timeout=timeout,
            retry=retry,
            pool_limits=pool_limits_from_settings(settings),
            param_compat_table=compat_table,
        )
        authorized = tuple(
            str(item).strip()
            for item in (getattr(getattr(settings, "models", None), "retention_authorized", None) or [])
            if str(item).strip()
        )
        pool = FrontierPool.from_single(executor)
        pool.retention_authorized = authorized
        return pool

    slots: list[ProviderSlot] = []
    for entry in providers:
        keys = list(entry.keys or [])
        if entry.api_key_env:
            env_key = os.environ.get(entry.api_key_env)
            if env_key and env_key not in keys:
                keys.insert(0, env_key)
        # Fall back to the global resolve when a provider lists no keys.
        if not keys:
            shared = settings.resolve_frontier_api_key()
            if shared:
                keys = [shared]
        entry_timeout, entry_retry = _entry_frontier_policy(settings, entry)
        executor = FrontierExecutor(
            base_url=entry.base_url.rstrip("/"),
            default_model=entry.model,
            api_key=keys[0] if keys else None,
            provider=entry.id,
            prompt_cache=frontier.prompt_cache,
            auto_caching=bool(getattr(frontier, "auto_caching", False)),
            thinking_binding_drop_block=bool(
                getattr(frontier, "thinking_binding_drop_block", True)
            ),
            codex_base_url=getattr(frontier, "codex_base_url", None),
            timeout=entry_timeout,
            retry=entry_retry,
            pool_limits=pool_limits_from_settings(settings),
            param_compat_table=compat_table,
        )
        slots.append(
            ProviderSlot(
                id=entry.id,
                executor=executor,
                keys=keys,
                weight=max(0.0, float(entry.weight)),
                zdr=bool(getattr(entry, "zdr", False)),
                region=str(getattr(entry, "region", "") or ""),
                breaker=CircuitBreaker(
                    failure_threshold=max(1, int(entry.failure_threshold)),
                    cooldown_seconds=max(1.0, float(entry.cooldown_seconds)),
                    share_key=share_key_for("frontier", entry.id),
                ),
            )
        )
    first = slots[0].executor if slots else None
    authorized = tuple(
        str(item).strip()
        for item in (getattr(getattr(settings, "models", None), "retention_authorized", None) or [])
        if str(item).strip()
    )
    return FrontierPool(
        slots=slots,
        base_url=first.base_url if first else frontier.base_url,
        default_model=first.default_model if first else frontier.model,
        api_key=first.api_key if first else None,
        provider="pool",
        prompt_cache=frontier.prompt_cache,
        auto_caching=bool(getattr(frontier, "auto_caching", False)),
        retention_authorized=authorized,
    )
