"""SSE / NDJSON keepalive while waiting for the first upstream chunk (#276)."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable

SSE_KEEPALIVE_FRAME = ": keepalive\n\n"
NDJSON_KEEPALIVE_FRAME = "\n"
_SENTINEL = object()


async def stream_with_keepalive(
    source: AsyncIterator[str],
    *,
    interval_seconds: float,
    frame: str = SSE_KEEPALIVE_FRAME,
    on_cancel: Callable[[], None] | None = None,
) -> AsyncIterator[str]:
    """Emit *frame* until the first chunk from *source*, then pass through.

    Closing this generator (client disconnect) cancels *source* and, when the
    caller passed *on_cancel*, records the abandon. A source error is not a cancel.
    """
    if interval_seconds <= 0:
        finished = False
        failed = False
        aiter = source.__aiter__()
        try:
            while True:
                try:
                    chunk = await aiter.__anext__()
                except StopAsyncIteration:
                    finished = True
                    break
                yield chunk
        except Exception:
            failed = True
            raise
        finally:
            if not finished and not failed and on_cancel is not None:
                on_cancel()
            aclose = getattr(aiter, "aclose", None)
            if aclose is not None:
                await aclose()
        return

    queue: asyncio.Queue[object] = asyncio.Queue()

    async def pump() -> None:
        try:
            async for chunk in source:
                await queue.put(chunk)
        except Exception as exc:
            await queue.put(exc)
        finally:
            await queue.put(_SENTINEL)

    pump_task = asyncio.create_task(pump())
    awaiting_first = True
    finished = False
    failed = False
    try:
        while True:
            try:
                if awaiting_first:
                    item = await asyncio.wait_for(queue.get(), timeout=interval_seconds)
                else:
                    item = await queue.get()
            except asyncio.TimeoutError:
                yield frame
                continue

            if item is _SENTINEL:
                finished = True
                return
            if isinstance(item, Exception):
                failed = True
                raise item
            yield item  # type: ignore[misc]
            awaiting_first = False
    finally:
        if not pump_task.done():
            pump_task.cancel()
            try:
                await pump_task
            except asyncio.CancelledError:
                pass
        if not finished and not failed and on_cancel is not None:
            on_cancel()
