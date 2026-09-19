"""Request-scoped wall-clock budget across cache, local, and frontier hops.

The absolute deadline is the same arithmetic ``with_retries`` uses
(``absolute_deadline`` / ``exceeds_deadline`` / ``remaining_seconds``). A hop
must not keep its own copy of that clock.
"""

from __future__ import annotations

import asyncio
import time
from contextlib import asynccontextmanager, contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Callable, Iterator

from daari.router.retry import absolute_deadline, exceeds_deadline, remaining_seconds

_STATE: ContextVar[_DeadlineState | None] = ContextVar("daari_request_deadline", default=None)


class RequestDeadlineExceeded(Exception):
    """The request's wall-clock budget ran out before a tier could answer."""

    def __init__(self, *, deadline_seconds: float, elapsed_ms: int, tiers: list[str]) -> None:
        self.deadline_seconds = float(deadline_seconds)
        self.elapsed_ms = int(elapsed_ms)
        self.tiers = list(tiers)
        super().__init__(
            f"request deadline exceeded (deadline {self.deadline_seconds:g}s, "
            f"elapsed {self.elapsed_ms}ms)"
        )


@dataclass
class _DeadlineState:
    started: float
    deadline: float
    budget_seconds: float
    metrics: Any
    monotonic: Callable[[], float]
    tiers: list[str] = field(default_factory=list)
    logged: bool = False


def parse_deadline_ms(raw: str | None) -> int | None:
    """Parse ``X-Daari-Deadline-Ms``. Blank or non-numeric values are absent."""
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    try:
        return max(0, int(text))
    except ValueError:
        return None


def resolve_deadline_seconds(
    header_ms: int | None,
    setting_seconds: float | None,
) -> float | None:
    """Header wins. Both absent (setting None or <= 0) means no request deadline."""
    if header_ms is not None:
        return max(0.0, float(header_ms)) / 1000.0
    if setting_seconds is None or float(setting_seconds) <= 0:
        return None
    return float(setting_seconds)


def deadline_active() -> bool:
    return _STATE.get() is not None


def reraise_deadline(exc: BaseException) -> None:
    if isinstance(exc, RequestDeadlineExceeded):
        raise exc


@contextmanager
def bind_request_deadline(
    seconds: float,
    *,
    metrics: Any = None,
    monotonic: Callable[[], float] | None = None,
) -> Iterator[_DeadlineState]:
    """Bind a wall-clock budget for the current task. ``seconds`` of 0 is already spent."""
    clock = monotonic or time.monotonic
    started = clock()
    if seconds > 0:
        deadline = absolute_deadline(started, seconds)
        if deadline is None:
            deadline = started + float(seconds)
    else:
        deadline = started
    state = _DeadlineState(
        started=started,
        deadline=deadline,
        budget_seconds=float(seconds),
        metrics=metrics,
        monotonic=clock,
    )
    token = _STATE.set(state)
    try:
        yield state
    finally:
        _STATE.reset(token)


def _exhaust(state: _DeadlineState, now: float) -> None:
    elapsed_ms = int(max(0.0, (now - state.started) * 1000))
    if not state.logged:
        state.logged = True
        metrics = state.metrics
        if metrics is not None and hasattr(metrics, "record_deadline_exhausted"):
            try:
                metrics.record_deadline_exhausted()
            except Exception:  # noqa: BLE001 — metrics must never hide the deadline
                pass
        from daari.gateway.request_log import log_gateway_event

        log_gateway_event(
            "request_deadline_exceeded",
            {
                "tiers_attempted": list(state.tiers),
                "elapsed_ms": elapsed_ms,
                "deadline_seconds": state.budget_seconds,
            },
        )
    raise RequestDeadlineExceeded(
        deadline_seconds=state.budget_seconds,
        elapsed_ms=elapsed_ms,
        tiers=list(state.tiers),
    )


def guard_upstream(tier: str) -> float | None:
    """Refuse an upstream hop when the budget is already spent.

    Returns remaining seconds, or None when this request has no deadline.
    The tier is recorded only when the hop is allowed.
    """
    state = _STATE.get()
    if state is None:
        return None
    now = state.monotonic()
    remaining = remaining_seconds(state.deadline, now)
    if remaining is None or remaining <= 0 or exceeds_deadline(state.deadline, now):
        _exhaust(state, now)
    if not state.tiers or state.tiers[-1] != tier:
        state.tiers.append(tier)
    return remaining


def clamp_timeout(configured: float, remaining: float | None) -> float:
    """``min(configured, remaining)`` when a budget is set; otherwise ``configured``."""
    if remaining is None:
        return float(configured)
    if remaining <= 0:
        return 0.0
    return min(float(configured), float(remaining))


def nonstream_timeout(configured: float, tier: str) -> float:
    """Effective httpx timeout for one non-streaming upstream call."""
    return clamp_timeout(configured, guard_upstream(tier))


async def aiter_with_ttft_deadline(source: AsyncIterator[Any]) -> AsyncIterator[Any]:
    """Bound time-to-first-item. Later items are not cancelled by the deadline."""
    iterator = source.__aiter__()
    state = _STATE.get()
    if state is None:
        async for item in iterator:
            yield item
        return
    now = state.monotonic()
    remaining = remaining_seconds(state.deadline, now)
    if remaining is None or remaining <= 0 or exceeds_deadline(state.deadline, now):
        _exhaust(state, now)
    try:
        first = await asyncio.wait_for(anext(iterator), timeout=remaining)
    except StopAsyncIteration:
        return
    except TimeoutError:
        _exhaust(state, state.monotonic())
    yield first
    async for item in iterator:
        yield item


async def _enter(cm: Any, state: _DeadlineState | None) -> Any:
    if state is None:
        return await cm.__aenter__()
    now = state.monotonic()
    remaining = remaining_seconds(state.deadline, now)
    if remaining is None or remaining <= 0 or exceeds_deadline(state.deadline, now):
        _exhaust(state, now)
    try:
        return await asyncio.wait_for(cm.__aenter__(), timeout=remaining)
    except TimeoutError:
        try:
            await cm.__aexit__(None, None, None)
        except Exception:  # noqa: BLE001 — best-effort close after a cancelled open
            pass
        _exhaust(state, state.monotonic())


@asynccontextmanager
async def deadline_bounded_stream(client: Any, method: str, url: str, **kwargs: Any) -> AsyncIterator[Any]:
    """Open a stream. The deadline bounds connect and time-to-headers, not later reads.

    The client itself keeps its configured timeout so an established stream is
    not killed when the request budget elapses mid-flight.
    """
    cm = client.stream(method, url, **kwargs)
    response = await _enter(cm, _STATE.get())
    try:
        yield response
    finally:
        await cm.__aexit__(None, None, None)
