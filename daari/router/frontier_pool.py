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
from daari.observability.trace import add_step
from daari.router.circuit_breaker import CircuitBreaker
from daari.router.frontier import FrontierExecutor


@dataclass
class ProviderSlot:
    id: str
    executor: FrontierExecutor
    keys: list[str]
    weight: float = 1.0
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
        if not self.keys:
            return self.executor.api_key
        # Weighted: duplicate entries by rounded weight, then cycle.
        if self.weight <= 0:
            return next(self._key_cycle)
        return next(self._key_cycle)


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

        errors: list[str] = []
        for slot in self.slots:
            if not slot.breaker.allow():
                add_step(
                    "frontier_skip",
                    provider=slot.id,
                    reason="circuit_open",
                    state=slot.breaker.state,
                )
                continue
            key = slot.pick_key()
            if not key:
                errors.append(f"{slot.id}:no_key")
                continue
            # Rotate the key onto the executor for this attempt.
            slot.executor.api_key = key
            add_step(
                "frontier_try",
                provider=slot.id,
                model=slot.executor.default_model,
                key_fingerprint=key[-4:] if len(key) >= 4 else "****",
            )
            try:
                response = await slot.executor.execute(
                    request,
                    escalated_from=escalated_from,
                    local_confidence=local_confidence,
                )
                slot.breaker.record_success()
                add_step("frontier_ok", provider=slot.id, model=response.model)
                # Surface which provider won for ledger/meta.
                response.daari_meta.provider_id = slot.id
                return response
            except Exception as exc:  # noqa: BLE001 — try next provider
                slot.breaker.record_failure()
                errors.append(f"{slot.id}:{type(exc).__name__}")
                add_step(
                    "frontier_fail",
                    provider=slot.id,
                    error_type=type(exc).__name__,
                    error=str(exc)[:200],
                    breaker=slot.breaker.state,
                )
                continue

        raise RuntimeError(
            "all frontier providers failed or open: " + (", ".join(errors) or "none tried")
        )


def build_frontier_pool(settings: Any) -> FrontierPool:
    """Build a pool from FrontierSettings.providers, falling back to scalars."""
    frontier = settings.frontier
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
        )
        return FrontierPool.from_single(executor)

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
        executor = FrontierExecutor(
            base_url=entry.base_url.rstrip("/"),
            default_model=entry.model,
            api_key=keys[0] if keys else None,
            provider=entry.id,
            prompt_cache=frontier.prompt_cache,
        )
        slots.append(
            ProviderSlot(
                id=entry.id,
                executor=executor,
                keys=keys,
                weight=max(0.0, float(entry.weight)),
                breaker=CircuitBreaker(
                    failure_threshold=max(1, int(entry.failure_threshold)),
                    cooldown_seconds=max(1.0, float(entry.cooldown_seconds)),
                ),
            )
        )
    first = slots[0].executor if slots else None
    return FrontierPool(
        slots=slots,
        base_url=first.base_url if first else frontier.base_url,
        default_model=first.default_model if first else frontier.model,
        api_key=first.api_key if first else None,
        provider="pool",
        prompt_cache=frontier.prompt_cache,
    )
