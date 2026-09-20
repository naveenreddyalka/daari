from __future__ import annotations

from dataclasses import dataclass, field
from threading import Lock
from typing import Any

# Prometheus histogram upper bounds (ms). Keep sorted; +Inf is implicit.
LATENCY_BUCKETS_MS: tuple[float, ...] = (5, 25, 50, 100, 250, 500, 1000, 2500, 5000, 10000)
# TTFT tends to be shorter than full request latency; reuse the same bounds.
TTFT_BUCKETS_MS: tuple[float, ...] = LATENCY_BUCKETS_MS


def histogram_percentile_ms(
    buckets: dict[float | str, int],
    *,
    count: int,
    percentile: float,
) -> float | None:
    """Approximate a percentile from exclusive histogram buckets (#529).

    ``buckets`` maps upper bound → count in that exclusive bucket (same shape
    as ``TtftStats.buckets``). Returns the bucket upper bound covering the
    target rank, or None when there are no samples.
    """
    if count <= 0:
        return None
    mark = max(0.0, min(1.0, float(percentile)))
    # Ceiling of mark * count without importing math.
    target = int(mark * count)
    if target < mark * count:
        target += 1
    target = max(1, target)
    cumulative = 0
    for bound in TTFT_BUCKETS_MS:
        cumulative += int(buckets.get(bound, 0))
        if cumulative >= target:
            return float(bound)
    if int(buckets.get("+Inf", 0)) > 0:
        return float("inf")
    return float(TTFT_BUCKETS_MS[-1]) if cumulative else None


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
class TtftStats:
    """Stream time-to-first-token histogram for one tier (#508)."""

    count: int = 0
    total_ttft_ms: int = 0
    buckets: dict[float | str, int] = field(default_factory=dict)

    def observe(self, ttft_ms: int) -> None:
        self.count += 1
        self.total_ttft_ms += max(0, int(ttft_ms))
        for bound in TTFT_BUCKETS_MS:
            if ttft_ms <= bound:
                self.buckets[bound] = self.buckets.get(bound, 0) + 1
                return
        self.buckets["+Inf"] = self.buckets.get("+Inf", 0) + 1


@dataclass
class Metrics:
    tiers: dict[str, TierStats] = field(default_factory=dict)
    ttft: dict[str, TtftStats] = field(default_factory=dict)
    errors: int = 0
    escalations: int = 0
    guardrails: dict[str, int] = field(default_factory=dict)
    boundaries: dict[str, int] = field(default_factory=dict)
    cache_false_hits_avoided: int = 0
    upstream_retries: int = 0
    backends: dict[str, int] = field(default_factory=dict)
    tier_shadow: dict[str, int] = field(default_factory=dict)
    budget_alerts: dict[str, int] = field(default_factory=dict)
    soft_warnings: dict[str, int] = field(default_factory=dict)
    rejects: dict[str, int] = field(default_factory=dict)
    ttft_preferences: dict[str, int] = field(default_factory=dict)
    mcp_tool_calls: dict[str, int] = field(default_factory=dict)
    cancelled: dict[str, int] = field(default_factory=dict)
    deadline_exhausted: int = 0
    _lock: Lock = field(default_factory=Lock, repr=False)

    def record(
        self,
        tier: str,
        *,
        cache_hit: bool = False,
        latency_ms: int = 0,
        backend_id: str | None = None,
    ) -> None:
        with self._lock:
            stats = self.tiers.setdefault(tier, TierStats())
            stats.count += 1
            if cache_hit:
                stats.cache_hits += 1
            stats.total_latency_ms += latency_ms
            if latency_ms > 0:
                stats.observe_latency(latency_ms)
            if backend_id:
                self.backends[backend_id] = self.backends.get(backend_id, 0) + 1

    def record_ttft(self, tier: str, *, ttft_ms: int) -> None:
        """Record stream time-to-first-token. Non-stream requests omit TTFT (#508)."""
        with self._lock:
            self.ttft.setdefault(tier, TtftStats()).observe(ttft_ms)

    def record_error(self) -> None:
        with self._lock:
            self.errors += 1

    def record_escalation(self) -> None:
        with self._lock:
            self.escalations += 1

    def record_guardrail(self, action: str) -> None:
        with self._lock:
            self.guardrails[action] = self.guardrails.get(action, 0) + 1

    def record_boundary(self, label: str, stage: str) -> None:
        key = f"{stage}:{label}"
        with self._lock:
            self.boundaries[key] = self.boundaries.get(key, 0) + 1

    def record_false_hit_avoided(self) -> None:
        """An L1 candidate that cleared cosine but failed verification (#168)."""
        with self._lock:
            self.cache_false_hits_avoided += 1

    def record_upstream_retry(self) -> None:
        """A transient upstream failure that was retried rather than surfaced (#159).

        A rising count means backoff is absorbing instability the client never
        saw; a flat count with rising errors means failures are not retryable.
        """
        with self._lock:
            self.upstream_retries += 1

    def record_tier_shadow(self, *, agreed: bool) -> None:
        """A sampled local-tier answer was replayed at a comparison tier (#318)."""
        key = "agree" if agreed else "disagree"
        with self._lock:
            self.tier_shadow[key] = self.tier_shadow.get(key, 0) + 1

    def record_budget_alert(self, *, scope: str, threshold: float) -> None:
        key = f"{scope}:{threshold:g}"
        with self._lock:
            self.budget_alerts[key] = self.budget_alerts.get(key, 0) + 1

    def record_soft_warning(self, kind: str) -> None:
        """Soft band before hard 402/429 (request_quota or rate_limit, #526)."""
        with self._lock:
            self.soft_warnings[kind] = self.soft_warnings.get(kind, 0) + 1

    def record_reject(self, kind: str) -> None:
        """Hard 402/429 deny (budget, request_quota, or rate_limit, #551)."""
        with self._lock:
            self.rejects[kind] = self.rejects.get(kind, 0) + 1

    def record_ttft_preference(self, *, from_tier: str, to_tier: str) -> None:
        """TTFT-aware routing rewrote the heuristic pick (#539)."""
        key = f"{from_tier}:{to_tier}"
        with self._lock:
            self.ttft_preferences[key] = self.ttft_preferences.get(key, 0) + 1

    def record_mcp_tool_call(self, *, tool: str, outcome: str) -> None:
        """MCP ingress tools/call outcome (ok, deny, error, guardrail) (#603)."""
        key = f"{tool}:{outcome}"
        with self._lock:
            self.mcp_tool_calls[key] = self.mcp_tool_calls.get(key, 0) + 1

    def record_cancelled(self, phase: str) -> None:
        """Client abandoned the request before upstream work finished (#769)."""
        with self._lock:
            self.cancelled[phase] = self.cancelled.get(phase, 0) + 1

    def record_deadline_exhausted(self) -> None:
        """A request-scoped deadline ran out before a tier could finish (#771)."""
        with self._lock:
            self.deadline_exhausted += 1

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
            ttft: dict[str, dict[str, Any]] = {}
            for tier, stats in sorted(self.ttft.items()):
                ttft[tier] = {
                    "count": stats.count,
                    "total_ttft_ms": stats.total_ttft_ms,
                    "buckets": dict(stats.buckets),
                }
            return {
                "tiers": tiers,
                "ttft": ttft,
                "errors": self.errors,
                "escalations": self.escalations,
                "guardrails": dict(self.guardrails),
                "boundaries": dict(self.boundaries),
                "cache_false_hits_avoided": self.cache_false_hits_avoided,
                "upstream_retries": self.upstream_retries,
                "backends": dict(self.backends),
                "tier_shadow": dict(self.tier_shadow),
                "budget_alerts": dict(self.budget_alerts),
                "soft_warnings": dict(self.soft_warnings),
                "rejects": dict(self.rejects),
                "ttft_preferences": dict(self.ttft_preferences),
                "mcp_tool_calls": dict(self.mcp_tool_calls),
                "cancelled": dict(self.cancelled),
                "deadline_exhausted": self.deadline_exhausted,
            }
