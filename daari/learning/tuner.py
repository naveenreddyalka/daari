"""Per-category confidence thresholds derived from outcomes (Phase D1c).

Categories where local tiers reliably succeed get a slightly lower
escalation bar (fewer wasted escalations); categories with heavy
escalation or explicit rejects get a slightly higher one (escalate
sooner). Adjustments are one bounded step from the global threshold,
require real evidence, and are recorded in the request trace — the
tuner nudges, it never rewrites config.
"""

from __future__ import annotations

import time
from typing import Any

STEP = 0.05
LOWER_BOUND = 0.5
UPPER_BOUND = 0.9

# Evidence bands: relax when clearly good, tighten when clearly bad,
# otherwise leave the global threshold alone.
GOOD_MAX_ESCALATION_RATE = 0.05
GOOD_MAX_REJECT_RATE = 0.05
BAD_MIN_ESCALATION_RATE = 0.30
BAD_MIN_REJECT_RATE = 0.20


class RoutingTuner:
    def __init__(
        self,
        feedback_store: Any,
        *,
        base_threshold: float = 0.7,
        min_samples: int = 50,
        days: int = 7,
        refresh_seconds: float = 60.0,
    ) -> None:
        self.feedback_store = feedback_store
        self.base_threshold = base_threshold
        self.min_samples = max(1, min_samples)
        self.days = days
        self.refresh_seconds = refresh_seconds
        self._stats: dict[str, dict[str, dict[str, Any]]] = {}
        self._fetched_at: float | None = None

    def _fresh_stats(self) -> dict[str, dict[str, dict[str, Any]]]:
        now = time.monotonic()
        if self._fetched_at is None or now - self._fetched_at >= self.refresh_seconds:
            try:
                self._stats = self.feedback_store.stats(days=self.days)
            except Exception:
                self._stats = {}
            self._fetched_at = now
        return self._stats

    def threshold_for(self, category: str) -> float:
        tiers = self._fresh_stats().get(category)
        if not tiers:
            return self.base_threshold
        # Escalated requests are recorded as L6 rows (the final tier), so
        # evidence must span every tier for the category.
        outcomes = escalated = rejects = 0
        for evidence in tiers.values():
            outcomes += evidence["outcomes"]
            escalated += evidence["escalated"]
            rejects += evidence["rejects"]
        if outcomes < self.min_samples:
            return self.base_threshold
        escalation_rate = escalated / outcomes
        reject_rate = rejects / outcomes
        tuned = self.base_threshold
        if escalation_rate >= BAD_MIN_ESCALATION_RATE or reject_rate >= BAD_MIN_REJECT_RATE:
            tuned = self.base_threshold + STEP
        elif escalation_rate <= GOOD_MAX_ESCALATION_RATE and reject_rate <= GOOD_MAX_REJECT_RATE:
            tuned = self.base_threshold - STEP
        return min(UPPER_BOUND, max(LOWER_BOUND, round(tuned, 4)))
