from __future__ import annotations

from dataclasses import dataclass, field
from threading import Lock


@dataclass
class TierStats:
    count: int = 0
    cache_hits: int = 0
    total_latency_ms: int = 0

    @property
    def avg_latency_ms(self) -> float:
        if self.count == 0:
            return 0.0
        return self.total_latency_ms / self.count


@dataclass
class Metrics:
    tiers: dict[str, TierStats] = field(default_factory=dict)
    errors: int = 0
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

    def record_error(self) -> None:
        with self._lock:
            self.errors += 1

    def snapshot(self) -> dict[str, dict[str, float | int]]:
        with self._lock:
            return {
                tier: {
                    "count": stats.count,
                    "cache_hits": stats.cache_hits,
                    "avg_latency_ms": round(stats.avg_latency_ms, 1),
                }
                for tier, stats in sorted(self.tiers.items())
            }
