"""Per-provider circuit breaker for L6 frontier calls (issue #109).

States: closed (normal) → open (after N consecutive failures) → half-open
(after cooldown, one probe allowed) → closed on success or open again on fail.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from threading import Lock


@dataclass
class CircuitBreaker:
    failure_threshold: int = 3
    cooldown_seconds: float = 30.0
    failures: int = 0
    opened_at: float | None = None
    _lock: Lock = field(default_factory=Lock, repr=False)

    def allow(self) -> bool:
        with self._lock:
            if self.opened_at is None:
                return True
            if time.monotonic() - self.opened_at >= self.cooldown_seconds:
                # Half-open: allow a single probe.
                return True
            return False

    def record_success(self) -> None:
        with self._lock:
            self.failures = 0
            self.opened_at = None

    def record_failure(self) -> None:
        with self._lock:
            self.failures += 1
            if self.failures >= self.failure_threshold:
                self.opened_at = time.monotonic()

    @property
    def state(self) -> str:
        with self._lock:
            if self.opened_at is None:
                return "closed"
            if time.monotonic() - self.opened_at >= self.cooldown_seconds:
                return "half_open"
            return "open"
