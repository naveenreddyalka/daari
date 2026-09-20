"""Cancel in-flight router work when the client hangs up (#769)."""

from __future__ import annotations

import asyncio
from typing import Any

from daari.gateway.request_log import log_gateway_event

# Short enough that an abandoned GPU call stops quickly, long enough that a
# finished route is returned without an extra sleep.
_POLL_SECONDS = 0.05


class ClientDisconnected(Exception):
    """The client went away. Not a backend failure — handlers answer 499."""


def note_request_cancelled(metrics: Any, phase: str, *, model: str = "") -> None:
    if metrics is not None and hasattr(metrics, "record_cancelled"):
        metrics.record_cancelled(phase)
    log_gateway_event("request_cancelled", {"phase": phase, "model": model or ""})


async def _client_gone(request: Any) -> bool:
    try:
        return bool(await request.is_disconnected())
    except asyncio.CancelledError:
        raise
    except Exception:
        return False


async def _cancel_task(task: asyncio.Task[Any]) -> None:
    if task.done():
        return
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        return


async def await_unless_disconnected(
    request: Any,
    awaitable: Any,
    *,
    metrics: Any,
    phase: str,
    model: str = "",
) -> Any:
    """Await *awaitable*, cancelling it if the client disconnects.

    A disconnect (or cancellation of this task) cancels the inner task so the
    httpx call inside the executor observes ``CancelledError``.
    """
    task: asyncio.Task[Any] = asyncio.ensure_future(awaitable)
    try:
        while not task.done():
            try:
                await asyncio.wait_for(asyncio.shield(task), timeout=_POLL_SECONDS)
            except TimeoutError:
                pass
            if task.done():
                break
            if await _client_gone(request):
                await _cancel_task(task)
                note_request_cancelled(metrics, phase, model=model)
                raise ClientDisconnected()
        return task.result()
    except asyncio.CancelledError:
        if not task.done():
            await _cancel_task(task)
            note_request_cancelled(metrics, phase, model=model)
        raise
