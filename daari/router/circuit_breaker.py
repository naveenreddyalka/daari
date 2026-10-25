"""Per-provider circuit breaker for L6 frontier calls (issue #109).

States: closed (normal) → open (after N consecutive failures) → half-open
(after cooldown, one probe allowed) → closed on success or open again on fail.

When ``share_key`` is set and ``cache.backend=redis``, open/reject state is
fleet-shared via Redis (#1908). Redis errors fail open to process-local state.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from threading import Lock
from typing import Any


def counts_as_hard_provider_failure(exc: BaseException) -> bool:
    """429 and 529 are transient overloads, not hard provider failures.

    They share a class: retry with backoff, and do not open the circuit.
    """
    from daari.router.retry import status_of

    return status_of(exc) not in {429, 529}


def _breaker_store_client() -> Any | None:
    from daari.router import breaker_redis

    return breaker_redis.breaker_redis_client()


@dataclass
class CircuitBreaker:
    failure_threshold: int = 3
    cooldown_seconds: float = 30.0
    failures: int = 0
    opened_at: float | None = None
    opened_at_wall: float | None = None
    share_key: str | None = None
    rejects: int = 0
    _lock: Lock = field(default_factory=Lock, repr=False)

    def _note_reject_unlocked(self) -> None:
        from daari.router import breaker_redis

        shared = breaker_redis.incr_shared_rejects(
            self.share_key or "",
            cooldown_seconds=float(self.cooldown_seconds or 30.0),
        )
        if shared is None:
            self.rejects += 1
        else:
            self.rejects = shared

    def allow(self) -> bool:
        with self._lock:
            from daari.router import breaker_redis

            shared_open = (
                breaker_redis.load_shared_open(
                    self.share_key or "",
                    cooldown_seconds=float(self.cooldown_seconds or 30.0),
                )
                if self.share_key
                else None
            )
            if shared_open is True:
                self._note_reject_unlocked()
                return False
            if shared_open is False and _breaker_store_client() is not None:
                return True
            if self.opened_at is None:
                return True
            if time.monotonic() - self.opened_at >= self.cooldown_seconds:
                # Half-open: allow a single probe.
                return True
            self._note_reject_unlocked()
            return False

    def record_success(self) -> None:
        with self._lock:
            self.failures = 0
            self.opened_at = None
            self.opened_at_wall = None
            if self.share_key:
                from daari.router import breaker_redis

                breaker_redis.clear_shared_breaker(self.share_key)

    def record_failure(self) -> None:
        with self._lock:
            self.failures += 1
            if self.failures >= self.failure_threshold:
                self.opened_at = time.monotonic()
                self.opened_at_wall = time.time()
                if self.share_key:
                    from daari.router import breaker_redis

                    breaker_redis.publish_shared_open(
                        self.share_key,
                        cooldown_seconds=float(self.cooldown_seconds or 30.0),
                        failures=int(self.failures),
                    )

    def reject_count(self) -> int:
        with self._lock:
            if self.share_key:
                from daari.router import breaker_redis

                shared = breaker_redis.load_shared_rejects(self.share_key)
                if shared is not None:
                    return int(shared)
            return int(self.rejects)

    @property
    def state(self) -> str:
        with self._lock:
            if self.share_key:
                from daari.router import breaker_redis

                shared_open = breaker_redis.load_shared_open(
                    self.share_key,
                    cooldown_seconds=float(self.cooldown_seconds or 30.0),
                )
                if shared_open is True:
                    return "open"
                if shared_open is False and _breaker_store_client() is not None:
                    return "closed"
            if self.opened_at is None:
                return "closed"
            if time.monotonic() - self.opened_at >= self.cooldown_seconds:
                return "half_open"
            return "open"
