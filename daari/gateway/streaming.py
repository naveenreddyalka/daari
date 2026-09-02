"""SSE / NDJSON keepalive while waiting for the first upstream chunk (#276)."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

SSE_KEEPALIVE_FRAME = ": keepalive\n\n"
NDJSON_KEEPALIVE_FRAME = "\n"
_SENTINEL = object()


async def stream_with_keepalive(
    source: AsyncIterator[str],
    *,
    interval_seconds: float,
    frame: str = SSE_KEEPALIVE_FRAME,
) -> AsyncIterator[str]:
    """Emit *frame* until the first chunk from *source*, then pass through."""
    if interval_seconds <= 0:
        async for chunk in source:
            yield chunk
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
                return
            if isinstance(item, Exception):
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
