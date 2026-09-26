"""Coordinated graceful shutdown / admission drain (#1104)."""

from __future__ import annotations

import asyncio
from typing import Any

# Bound for awaiting fire-and-forget budget-alert tasks during lifespan teardown.
BUDGET_ALERT_DRAIN_TIMEOUT_SECONDS = 5.0


def begin_shutdown(app: Any) -> None:
    """Flip readiness to not-ready and stop admitting new in-flight work."""
    app.state.shutting_down = True
    tasks = getattr(app.state, "budget_alert_tasks", None)
    if tasks is None:
        app.state.budget_alert_tasks = set()
    limiter = getattr(app.state, "rate_limiter", None)
    begin_drain = getattr(limiter, "begin_drain", None)
    if callable(begin_drain):
        begin_drain()


def track_budget_alert_task(app: Any, task: asyncio.Task[Any]) -> asyncio.Task[Any]:
    """Register a budget-alert task so lifespan can await it on shutdown."""
    tasks: set[asyncio.Task[Any]] = getattr(app.state, "budget_alert_tasks", None) or set()
    app.state.budget_alert_tasks = tasks
    tasks.add(task)
    task.add_done_callback(tasks.discard)
    return task


async def await_budget_alert_tasks(
    app: Any, *, timeout: float = BUDGET_ALERT_DRAIN_TIMEOUT_SECONDS
) -> None:
    """Await outstanding budget-alert tasks with a bounded timeout."""
    tasks = list(getattr(app.state, "budget_alert_tasks", set()) or set())
    if not tasks:
        return
    bound = max(0.0, float(timeout))
    if bound <= 0:
        for task in tasks:
            if not task.done():
                task.cancel()
        return
    done, pending = await asyncio.wait(tasks, timeout=bound)
    for task in pending:
        task.cancel()
    if pending:
        await asyncio.gather(*pending, return_exceptions=True)
    _ = done
