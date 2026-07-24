from __future__ import annotations

from dataclasses import dataclass, field
from threading import Lock
from typing import Any

# Prometheus histogram upper bounds (ms). Keep sorted; +Inf is implicit.
LATENCY_BUCKETS_MS: tuple[float, ...] = (5, 25, 50, 100, 250, 500, 1000, 2500, 5000, 10000)


@dataclass
class TierStats:
    count: int = 0
    cache_hits: int = 0
    total_latency_ms: int = 0
    latency_buckets: dict[float | str, int] = field(default_factory=dict)

    @property
    def avg_latency_ms(self) -> float:
        if self.count == 0:
            return 0.0
        return self.total_latency_ms / self.count

    def observe_latency(self, latency_ms: int) -> None:
        for bound in LATENCY_BUCKETS_MS:
            if latency_ms <= bound:
                self.latency_buckets[bound] = self.latency_buckets.get(bound, 0) + 1
                return
        self.latency_buckets["+Inf"] = self.latency_buckets.get("+Inf", 0) + 1


@dataclass
class Metrics:
    tiers: dict[str, TierStats] = field(default_factory=dict)
    errors: int = 0
    escalations: int = 0
    guardrails: dict[str, int] = field(default_factory=dict)
    _lock: Lock = field(default_factory=Lock, repr=False)

    def record(
        self,
        tier: str,
        *,
        cache_hit: bool = False,
        latency_ms: int = 0,
    ) -> None:
        with self._lock:
            stats = self.tiers.setdefault(tier, TierStats())
            stats.count += 1
            if cache_hit:
                stats.cache_hits += 1
            stats.total_latency_ms += latency_ms
            if latency_ms > 0:
                stats.observe_latency(latency_ms)

    def record_error(self) -> None:
        with self._lock:
            self.errors += 1

    def record_escalation(self) -> None:
        with self._lock:
            self.escalations += 1

    def record_guardrail(self, action: str) -> None:
        with self._lock:
            self.guardrails[action] = self.guardrails.get(action, 0) + 1

    def snapshot(self, *, include_histograms: bool = False) -> dict[str, Any]:
        """Tier map for /v1/daari/stats. With include_histograms=True also
        returns {"tiers", "errors", "escalations", "guardrails"} for exporters."""
        with self._lock:
            tiers: dict[str, dict[str, Any]] = {}
            for tier, stats in sorted(self.tiers.items()):
                entry: dict[str, Any] = {
                    "count": stats.count,
                    "cache_hits": stats.cache_hits,
                    "avg_latency_ms": round(stats.avg_latency_ms, 1),
                }
                if include_histograms:
                    entry["total_latency_ms"] = stats.total_latency_ms
                    entry["latency_buckets"] = dict(stats.latency_buckets)
                tiers[tier] = entry
            if not include_histograms:
                return tiers
            return {
                "tiers": tiers,
                "errors": self.errors,
                "escalations": self.escalations,
                "guardrails": dict(self.guardrails),
            }
