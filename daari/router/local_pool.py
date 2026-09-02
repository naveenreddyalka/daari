"""Local inference pool: health checks, load balancing, circuit breakers (#170)."""

from __future__ import annotations

from dataclasses import dataclass, field, is_dataclass, replace
from typing import Any

from daari.gateway.internal import InternalRequest, InternalResponse
from daari.observability.trace import add_step
from daari.router.circuit_breaker import CircuitBreaker


class BackendUnavailable(Exception):
    """No healthy local backend can serve this tier."""

    def __init__(self, tier: str, detail: str = "") -> None:
        self.tier = tier
        self.detail = detail
        message = detail or f"All {tier} backends are down."
        super().__init__(message)


@dataclass
class LocalBackendSlot:
    id: str
    base_url: str
    kind: str = "ollama"
    model: str = ""
    tiers: list[str] = field(default_factory=lambda: ["L3", "L4", "L5"])
    breaker: CircuitBreaker = field(default_factory=CircuitBreaker)
    healthy: bool = True
    outstanding: int = 0
    last_check: str = "ok"
    requests: int = 0


async def check_model_backend(probe_url: str, timeout: float = 2.0) -> str:
    """Indirection so tests can patch this module without importing the gateway."""
    from daari.gateway.openai import check_model_backend as _check

    return await _check(probe_url, timeout)


@dataclass
class LocalBackendPool:
    slots: list[LocalBackendSlot]
    strategy: str = "least_outstanding"
    health_interval_seconds: float = 15.0
    checked: bool = False
    _rr: dict[str, int] = field(default_factory=dict)

    def slots_for(self, tier: str) -> list[LocalBackendSlot]:
        return [slot for slot in self.slots if tier in slot.tiers]

    def _eligible(
        self, tier: str, *, warm_models: set[str] | None = None
    ) -> list[LocalBackendSlot]:
        candidates = [
            slot
            for slot in self.slots_for(tier)
            if slot.healthy and slot.breaker.allow()
        ]
        if not candidates:
            return []
        warm_models = warm_models or set()
        warm = [slot for slot in candidates if slot.model and slot.model in warm_models]
        return warm or candidates

    def _choose(
        self, candidates: list[LocalBackendSlot], tier: str
    ) -> LocalBackendSlot:
        if self.strategy == "round_robin":
            index = self._rr.get(tier, 0)
            self._rr[tier] = index + 1
            return candidates[index % len(candidates)]
        return min(candidates, key=lambda slot: slot.outstanding)

    def pick(self, tier: str, *, warm_models: set[str] | None = None) -> LocalBackendSlot:
        candidates = self._eligible(tier, warm_models=warm_models)
        if not candidates:
            raise BackendUnavailable(tier)
        return self._choose(candidates, tier)

    def acquire(self, slot: LocalBackendSlot) -> None:
        slot.outstanding += 1

    def release(self, slot: LocalBackendSlot) -> None:
        slot.outstanding = max(0, slot.outstanding - 1)

    def bind_executor(self, slot: LocalBackendSlot, template: Any) -> Any:
        if slot.kind == "openai":
            from daari.router.openai_executor import OpenAICompatExecutor

            return OpenAICompatExecutor(
                base_url=slot.base_url.rstrip("/"),
                default_model=slot.model or getattr(template, "default_model", ""),
                tier=getattr(template, "tier", "L4"),
                timeout=getattr(template, "timeout", 120.0),
                retry=getattr(template, "retry", None),
                metrics=getattr(template, "metrics", None),
            )
        if not is_dataclass(template) or isinstance(template, type):
            return template
        bound = replace(template, base_url=slot.base_url.rstrip("/"))
        # replace() only copies dataclass fields. Tests (and some adapters)
        # patch execute/stream on the instance; keep those bindings.
        for name in ("execute", "stream"):
            if name in getattr(template, "__dict__", {}):
                setattr(bound, name, template.__dict__[name])
        return bound

    async def execute(
        self,
        tier: str,
        request: InternalRequest,
        *,
        executors: dict[str, Any] | None = None,
        template: Any | None = None,
        warm_models: set[str] | None = None,
    ) -> InternalResponse:
        errors: list[str] = []
        tried: set[str] = set()
        while True:
            remaining = [
                slot
                for slot in self._eligible(tier, warm_models=warm_models)
                if slot.id not in tried
            ]
            if not remaining:
                break
            slot = self._choose(remaining, tier)
            tried.add(slot.id)
            executor = (executors or {}).get(slot.id)
            if executor is None and template is not None:
                executor = self.bind_executor(slot, template)
            if executor is None:
                errors.append(f"{slot.id}:no_executor")
                continue
            self.acquire(slot)
            try:
                add_step(
                    "backend_pick",
                    tier=tier,
                    backend_id=slot.id,
                    strategy=self.strategy,
                )
                if slot.model:
                    request = request.model_copy(update={"model": slot.model})
                response = await executor.execute(request)
                slot.breaker.record_success()
                slot.requests += 1
                response.daari_meta.backend_id = slot.id
                return response
            except Exception as exc:  # noqa: BLE001 — try the next host
                slot.breaker.record_failure()
                errors.append(f"{slot.id}:{type(exc).__name__}")
                add_step(
                    "backend_fail",
                    backend_id=slot.id,
                    error_type=type(exc).__name__,
                    breaker=slot.breaker.state,
                )
            finally:
                self.release(slot)
        raise BackendUnavailable(tier, ", ".join(errors) or "none tried")

    def readiness(self) -> dict[str, Any]:
        backends = [
            {
                "id": slot.id,
                "base_url": slot.base_url,
                "healthy": slot.healthy,
                "status": slot.last_check,
                "outstanding": slot.outstanding,
            }
            for slot in self.slots
        ]
        l3 = self.slots_for("L3") or self.slots
        l3_up = [slot for slot in l3 if slot.healthy]
        all_up = all(slot.healthy for slot in self.slots) if self.slots else False
        if not self.slots or not l3_up:
            status, http_status = "not_ready", 503
        elif not all_up:
            status, http_status = "degraded", 200
        else:
            status, http_status = "ready", 200
        model_backend = "ok" if l3_up else (l3[0].last_check if l3 else "missing")
        if status == "degraded" and l3_up:
            model_backend = "ok"
        return {
            "status": status,
            "http_status": http_status,
            "model_backend": model_backend,
            "backends": backends,
        }

    def snapshot(self) -> dict[str, Any]:
        return {
            "strategy": self.strategy,
            "backends": [
                {
                    "id": slot.id,
                    "healthy": slot.healthy,
                    "outstanding": slot.outstanding,
                    "requests": slot.requests,
                    "last_check": slot.last_check,
                }
                for slot in self.slots
            ],
        }

    async def check_health(self) -> None:
        for slot in self.slots:
            probe = (
                f"{slot.base_url.rstrip('/')}/v1/models"
                if slot.kind in ("mlx", "openai")
                else f"{slot.base_url.rstrip('/')}/api/version"
            )
            result = await check_model_backend(probe)
            slot.last_check = result
            slot.healthy = result == "ok"
        self.checked = True


def build_local_pool(settings: Any) -> LocalBackendPool:
    cfg = getattr(getattr(settings, "routing", None), "local_pool", None)
    strategy = getattr(cfg, "strategy", None) or "least_outstanding"
    interval = float(getattr(cfg, "health_interval_seconds", 15.0) or 15.0)
    configured = list(getattr(cfg, "backends", None) or [])
    slots: list[LocalBackendSlot] = []
    if configured:
        for index, entry in enumerate(configured):
            url = (getattr(entry, "base_url", None) or settings.ollama.base_url).rstrip("/")
            tiers = list(getattr(entry, "tiers", None) or ["L3", "L4", "L5"])
            slots.append(
                LocalBackendSlot(
                    id=getattr(entry, "id", None) or f"backend-{index}",
                    base_url=url,
                    kind=getattr(entry, "kind", None) or "ollama",
                    model=getattr(entry, "model", None) or "",
                    tiers=tiers,
                    breaker=CircuitBreaker(
                        failure_threshold=max(1, int(getattr(entry, "failure_threshold", 3) or 3)),
                        cooldown_seconds=max(
                            1.0, float(getattr(entry, "cooldown_seconds", 30.0) or 30.0)
                        ),
                    ),
                )
            )
    else:
        slots.append(
            LocalBackendSlot(
                id="ollama",
                base_url=settings.ollama.base_url.rstrip("/"),
                kind="ollama",
                model=settings.models.l3,
                tiers=["L3", "L4", "L5"],
            )
        )
        mlx = getattr(settings, "mlx", None)
        if getattr(mlx, "enabled", False) and getattr(mlx, "models", None):
            slots.append(
                LocalBackendSlot(
                    id="mlx",
                    base_url=mlx.base_url.rstrip("/"),
                    kind="mlx",
                    model="",
                    tiers=list(mlx.models.keys()),
                )
            )
    return LocalBackendPool(
        slots=slots,
        strategy=strategy,
        health_interval_seconds=interval,
    )
