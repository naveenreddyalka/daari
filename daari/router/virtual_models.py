"""Named virtual models → ordered local/L6 candidate lists (#2023, #2052)."""

from __future__ import annotations

from dataclasses import dataclass, field
from threading import Lock
from typing import Any, Callable, Literal

Kind = Literal["local", "frontier"]
SelectionMode = Literal["ordered", "performance"]

DEFAULT_EWMA_ALPHA = 0.3


@dataclass
class CandidateEwma:
    latency_ms: float = 0.0
    error_rate: float = 0.0
    samples: int = 0


@dataclass
class VirtualModelPerformanceTracker:
    """In-process EWMA of per-candidate latency and error rate (#2052).

    Fleet/Redis sharing is intentionally out of scope for v1.
    """

    alpha: float = DEFAULT_EWMA_ALPHA
    _stats: dict[str, dict[str, CandidateEwma]] = field(default_factory=dict)
    _lock: Lock = field(default_factory=Lock, repr=False)

    def _update(
        self,
        virtual_model: str,
        candidate: str,
        *,
        latency_ms: float,
        error: bool,
    ) -> None:
        vm = (virtual_model or "").strip()
        cand = (candidate or "").strip()
        if not vm or not cand:
            return
        alpha = max(0.01, min(1.0, float(self.alpha)))
        with self._lock:
            by_cand = self._stats.setdefault(vm, {})
            row = by_cand.get(cand)
            if row is None:
                row = CandidateEwma(
                    latency_ms=float(latency_ms),
                    error_rate=1.0 if error else 0.0,
                    samples=1,
                )
                by_cand[cand] = row
                return
            err_obs = 1.0 if error else 0.0
            row.error_rate = (1.0 - alpha) * row.error_rate + alpha * err_obs
            if not error:
                row.latency_ms = (1.0 - alpha) * row.latency_ms + alpha * float(latency_ms)
            row.samples += 1

    def observe_success(
        self, virtual_model: str, candidate: str, *, latency_ms: float
    ) -> None:
        self._update(virtual_model, candidate, latency_ms=latency_ms, error=False)

    def observe_error(
        self, virtual_model: str, candidate: str, *, latency_ms: float = 0.0
    ) -> None:
        self._update(virtual_model, candidate, latency_ms=latency_ms, error=True)

    def stats_for(self, virtual_model: str, candidate: str) -> CandidateEwma:
        vm = (virtual_model or "").strip()
        cand = (candidate or "").strip()
        with self._lock:
            row = self._stats.get(vm, {}).get(cand)
            if row is None:
                return CandidateEwma()
            return CandidateEwma(
                latency_ms=row.latency_ms,
                error_rate=row.error_rate,
                samples=row.samples,
            )

    def snapshot(self) -> dict[str, dict[str, dict[str, float | int]]]:
        with self._lock:
            out: dict[str, dict[str, dict[str, float | int]]] = {}
            for vm, by_cand in self._stats.items():
                out[vm] = {
                    cand: {
                        "latency_ms": round(row.latency_ms, 3),
                        "error_rate": round(row.error_rate, 6),
                        "samples": int(row.samples),
                    }
                    for cand, row in by_cand.items()
                }
            return out


def order_virtual_candidates(
    candidates: list[str],
    *,
    mode: SelectionMode | str = "ordered",
    virtual_model: str = "",
    tracker: VirtualModelPerformanceTracker | None = None,
    breaker_open: Callable[[str], bool] | None = None,
) -> list[str]:
    """Return try-order for virtual-model candidates (#2052).

    ``ordered`` (default): config order, minus breaker-open ids.
    ``performance``: lowest EWMA error_rate, then latency, then config index;
    breaker-open candidates are omitted (skipped).
    """
    cleaned = [str(c).strip() for c in candidates if str(c).strip()]
    if breaker_open is not None:
        cleaned = [c for c in cleaned if not breaker_open(c)]
    if not cleaned:
        return []
    sel = (mode or "ordered").strip().lower()
    if sel != "performance" or tracker is None:
        return cleaned

    indexed = list(enumerate(cleaned))

    def _key(item: tuple[int, str]) -> tuple[float, float, int]:
        idx, cand = item
        row = tracker.stats_for(virtual_model, cand)
        # Round so EWMA residuals after a recovery window do not permanently
        # lose to a never-errored sibling (acceptance: recovers after decay).
        return (round(row.error_rate, 4), round(row.latency_ms, 1), idx)

    return [cand for _, cand in sorted(indexed, key=_key)]


def resolve_virtual_candidates(
    model: str | None,
    virtual_models: dict[str, list[str]] | None,
) -> list[str] | None:
    """Return the ordered candidate list when ``model`` is a configured virtual name."""
    name = (model or "").strip()
    if not name or not virtual_models:
        return None
    candidates = virtual_models.get(name)
    if not candidates:
        return None
    cleaned = [str(c).strip() for c in candidates if str(c).strip()]
    return cleaned or None


def candidate_breaker_open(router: Any, candidate: str, settings: Any) -> bool:
    """True when every known breaker for this candidate refuses traffic."""
    kind, target = classify_candidate(candidate, settings)
    if kind == "local":
        pool = getattr(router, "local_pool", None)
        if pool is None:
            return False
        slots = pool.slots_for(target) if hasattr(pool, "slots_for") else []
        if not slots:
            return False
        return all(not slot.breaker.allow() for slot in slots)

    frontier = getattr(router, "frontier", None)
    slots = getattr(frontier, "slots", None) if frontier is not None else None
    if not slots:
        return False
    return all(not getattr(slot, "breaker").allow() for slot in slots if getattr(slot, "breaker", None))


def classify_candidate(candidate: str, settings: Any) -> tuple[Kind, str]:
    """Map a candidate id to (``local``, tier) or (``frontier``, model_id)."""
    raw = (candidate or "").strip()
    upper = raw.upper()
    if upper in {"L3", "L4", "L5"}:
        return "local", upper
    if upper in {"L6", "FRONTIER"}:
        return "frontier", "L6"

    if settings is None:
        return "frontier", raw

    models = getattr(settings, "models", None)
    for tier, attr in (("L3", "l3"), ("L4", "l4"), ("L5", "l5")):
        configured = getattr(models, attr, None) if models is not None else None
        if configured and raw == configured:
            return "local", tier

    pool = getattr(getattr(settings, "routing", None), "local_pool", None)
    for backend in getattr(pool, "backends", None) or []:
        if getattr(backend, "model", "") == raw:
            tiers = [t.upper() for t in (getattr(backend, "tiers", None) or [])]
            for tier in ("L3", "L4", "L5"):
                if tier in tiers:
                    return "local", tier
            return "local", "L3"

    return "frontier", raw


def known_local_ids(settings: Any) -> set[str]:
    """Configured local model / tier ids doctor treats as known."""
    known = {"L3", "L4", "L5", "L6", "FRONTIER", "l3", "l4", "l5", "l6", "frontier"}
    if settings is None:
        return known
    models = getattr(settings, "models", None)
    for attr in ("l3", "l4", "l5"):
        value = getattr(models, attr, None) if models is not None else None
        if value:
            known.add(str(value))
    pool = getattr(getattr(settings, "routing", None), "local_pool", None)
    for backend in getattr(pool, "backends", None) or []:
        model = getattr(backend, "model", "") or ""
        if model:
            known.add(model)
        bid = getattr(backend, "id", "") or ""
        if bid:
            known.add(bid)
    frontier = getattr(settings, "frontier", None)
    default = getattr(frontier, "default_model", None) if frontier is not None else None
    if default:
        known.add(str(default))
    return known


def virtual_models_findings(settings: Any) -> list[str]:
    """Doctor findings for empty lists / unknown-looking candidate ids."""
    if settings is None:
        return []
    routing = getattr(settings, "routing", None)
    mapping = getattr(routing, "virtual_models", None) or {}
    if not mapping:
        return []
    known = known_local_ids(settings)
    findings: list[str] = []
    for name, candidates in mapping.items():
        cleaned = [str(c).strip() for c in (candidates or []) if str(c).strip()]
        if not cleaned:
            findings.append(f"routing.virtual_models[{name!r}] has an empty candidate list")
            continue
        for candidate in cleaned:
            if candidate in known:
                continue
            if "/" in candidate:
                # Provider-style frontier id (openai/gpt-4o-mini, openrouter/…).
                continue
            if candidate.upper() in {"L3", "L4", "L5", "L6", "FRONTIER"}:
                continue
            findings.append(
                f"routing.virtual_models[{name!r}] candidate {candidate!r} looks unknown "
                "(not a local tier, configured models.* id, or provider/model frontier id)"
            )
    return findings
