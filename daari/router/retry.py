"""Bounded retries with backoff for upstream calls (issue #159).

Every upstream call — Ollama, MLX, frontier — used to get exactly one attempt, so
a single transient 429 or connection reset failed the whole request. Retrying is
only safe because these calls are idempotent reads from daari's point of view: the
ledger is written after a response returns, not per attempt.

Two rules keep retries from making things worse:

- Only transient failures are retried. Retrying a 401 or a malformed body burns
  the budget and delays an error the caller must see anyway.
- The retry budget never outlives the request timeout. A backoff that would land
  past the deadline is not attempted, so retries cannot turn a slow request into
  a hung one.
"""

from __future__ import annotations

import asyncio
import random
import time
from dataclasses import dataclass, field
from email.utils import parsedate_to_datetime
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, TypeVar

import httpx

T = TypeVar("T")

RETRYABLE_STATUS = frozenset({408, 429, 500, 502, 503, 504})

RETRYABLE_EXCEPTIONS: tuple[type[BaseException], ...] = (
    httpx.ConnectError,
    httpx.ConnectTimeout,
    httpx.ReadTimeout,
    httpx.WriteTimeout,
    httpx.PoolTimeout,
    httpx.RemoteProtocolError,
    httpx.ReadError,
)


class RetryBudgetExhausted(Exception):
    """Raised when a retryable failure survived every attempt.

    Lets the frontier pool distinguish "this provider is genuinely unhealthy"
    from "do not retry this", so it only fails over once retries are spent.
    """

    def __init__(self, attempts: int, last: BaseException) -> None:
        self.attempts = attempts
        self.last = last
        super().__init__(f"upstream failed after {attempts} attempt(s): {last}")


def status_of(exc: BaseException) -> int | None:
    response = getattr(exc, "response", None)
    if response is not None and hasattr(response, "status_code"):
        return int(response.status_code)
    # Ollama raises its own error carrying the status directly.
    status = getattr(exc, "status_code", None)
    return int(status) if isinstance(status, int) else None


def is_retryable(exc: BaseException) -> bool:
    """True when another attempt could plausibly succeed."""
    status = status_of(exc)
    if status is not None:
        return status in RETRYABLE_STATUS
    return isinstance(exc, RETRYABLE_EXCEPTIONS)


def retry_after_seconds(exc: BaseException) -> float | None:
    """Seconds requested by a `Retry-After` header, if the server sent a usable one."""
    response = getattr(exc, "response", None)
    headers = getattr(response, "headers", None)
    if not headers:
        return None
    raw = headers.get("Retry-After")
    if not raw:
        return None
    try:
        return max(0.0, float(raw))
    except (TypeError, ValueError):
        pass
    try:
        when = parsedate_to_datetime(raw)
    except (TypeError, ValueError):
        return None
    if when is None:
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return max(0.0, (when - datetime.now(timezone.utc)).total_seconds())


@dataclass
class RetryPolicy:
    """Bounded exponential backoff with equal jitter.

    `attempts` counts the first try, so `attempts=3` means at most two retries.
    Jitter spreads retries from concurrent requests that failed together, which
    otherwise return in lockstep and re-create the load that caused the failure.
    """

    attempts: int = 3
    base_delay: float = 0.2
    max_delay: float = 5.0
    jitter: float = 0.5
    _random: random.Random = field(default_factory=random.Random, repr=False)

    def __post_init__(self) -> None:
        self.attempts = max(1, int(self.attempts))
        self.base_delay = max(0.0, float(self.base_delay))
        self.max_delay = max(0.0, float(self.max_delay))
        self.jitter = min(1.0, max(0.0, float(self.jitter)))

    @property
    def enabled(self) -> bool:
        return self.attempts > 1

    @classmethod
    def from_settings(cls, retry_settings: Any) -> RetryPolicy:
        return cls(
            attempts=getattr(retry_settings, "attempts", 3),
            base_delay=getattr(retry_settings, "base_delay_ms", 200) / 1000,
            max_delay=getattr(retry_settings, "max_delay_ms", 5000) / 1000,
            jitter=getattr(retry_settings, "jitter", 0.5),
        )

    def delay_for(self, retry_index: int) -> float:
        """Backoff before retry `retry_index` (0-based), jittered."""
        capped = min(self.base_delay * (2**retry_index), self.max_delay)
        if not self.jitter or capped <= 0:
            return capped
        # Equal jitter: half fixed, half random, so delay stays in [d/2, d].
        floor = capped * (1.0 - self.jitter)
        return floor + self._random.random() * (capped - floor)


async def run_upstream(
    operation: Callable[[], Awaitable[T]],
    *,
    upstream: str,
    policy: RetryPolicy | None = None,
    timeout: float | None = None,
    metrics: Any = None,
) -> T:
    """`with_retries` wired to daari's trace and metrics.

    Each retry becomes a trace step, so a slow request shows why it was slow, and
    increments `daari_upstream_retries_total`.
    """
    from daari.observability.trace import add_step

    def report(attempt: int, exc: BaseException, delay: float) -> None:
        add_step(
            "upstream_retry",
            upstream=upstream,
            attempt=attempt,
            error_type=type(exc).__name__,
            status=status_of(exc),
            delay_ms=int(delay * 1000),
        )
        if metrics is not None:
            try:
                metrics.record_upstream_retry()
            except Exception:  # noqa: BLE001 — metrics must never break a request
                pass

    return await with_retries(
        operation, policy=policy, timeout=timeout, on_retry=report
    )


async def with_retries(
    operation: Callable[[], Awaitable[T]],
    *,
    policy: RetryPolicy | None = None,
    sleep: Callable[[float], Any] | None = None,
    timeout: float | None = None,
    monotonic: Callable[[], float] = time.monotonic,
    on_retry: Callable[[int, BaseException, float], None] | None = None,
) -> T:
    """Run `operation`, retrying transient failures within the policy and deadline.

    `sleep` is injectable so tests do not wait; it may be sync or async.
    """
    policy = policy or RetryPolicy()
    started = monotonic()
    deadline = started + timeout if timeout else None
    last: BaseException | None = None

    for attempt in range(1, policy.attempts + 1):
        try:
            return await operation()
        except BaseException as exc:  # noqa: BLE001 — re-raised below
            if not is_retryable(exc) or attempt >= policy.attempts:
                raise
            delay = retry_after_seconds(exc)
            if delay is None:
                delay = policy.delay_for(attempt - 1)
            if deadline is not None and monotonic() + delay >= deadline:
                # Sleeping would push the retry past the caller's timeout, so the
                # honest outcome is the failure we already have.
                raise
            last = exc
            if on_retry is not None:
                on_retry(attempt, exc, delay)
            if delay > 0:
                result = sleep(delay) if sleep is not None else asyncio.sleep(delay)
                if asyncio.iscoroutine(result):
                    await result

    # Unreachable: the loop either returns or raises.
    raise RetryBudgetExhausted(policy.attempts, last or RuntimeError("no attempt made"))
