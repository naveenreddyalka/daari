"""SSE / NDJSON keepalive for the full stream lifetime (#276, #972)."""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import AsyncIterator, Callable

SSE_KEEPALIVE_FRAME = ": keepalive\n\n"
NDJSON_KEEPALIVE_FRAME = "\n"
_SENTINEL = object()

SSE_IDLE_ERROR_FRAME = (
    "data: "
    + json.dumps(
        {
            "error": {
                "type": "stream_idle_timeout",
                "message": "upstream produced no data within the idle timeout.",
            }
        }
    )
    + "\n\n"
)
NDJSON_IDLE_ERROR_FRAME = (
    json.dumps(
        {
            "error": {
                "type": "stream_idle_timeout",
                "message": "upstream produced no data within the idle timeout.",
            }
        }
    )
    + "\n"
)


async def stream_with_keepalive(
    source: AsyncIterator[str],
    *,
    interval_seconds: float,
    frame: str = SSE_KEEPALIVE_FRAME,
    on_cancel: Callable[[], None] | None = None,
    idle_timeout_seconds: float = 0.0,
    idle_error_frame: str | None = None,
) -> AsyncIterator[str]:
    """Relay *source*, emitting *frame* whenever the gap between chunks exceeds
    *interval_seconds* (entire stream, not only time-to-first-token).

    When *idle_timeout_seconds* > 0 and upstream stays silent that long, emit
    *idle_error_frame* (or a default SSE/NDJSON error) and end the stream.
    Closing this generator (client disconnect) cancels *source* and, when the
    caller passed *on_cancel*, records the abandon. A source error is not a cancel.
    """
    idle_timeout = max(0.0, float(idle_timeout_seconds or 0.0))
    if idle_error_frame is None:
        idle_error_frame = (
            NDJSON_IDLE_ERROR_FRAME
            if frame == NDJSON_KEEPALIVE_FRAME
            else SSE_IDLE_ERROR_FRAME
        )

    if interval_seconds <= 0 and idle_timeout <= 0:
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
    finished = False
    failed = False
    last_chunk_at = time.monotonic()
    # Poll at the tighter of keepalive interval and idle timeout.
    poll = interval_seconds if interval_seconds > 0 else idle_timeout
    if idle_timeout > 0 and interval_seconds > 0:
        poll = min(interval_seconds, idle_timeout)
    try:
        while True:
            try:
                item = await asyncio.wait_for(queue.get(), timeout=poll)
            except asyncio.TimeoutError:
                now = time.monotonic()
                silent = now - last_chunk_at
                if idle_timeout > 0 and silent >= idle_timeout:
                    yield idle_error_frame
                    finished = True
                    return
                if interval_seconds > 0 and silent >= interval_seconds:
                    yield frame
                continue

            if item is _SENTINEL:
                finished = True
                return
            if isinstance(item, Exception):
                failed = True
                raise item
            yield item  # type: ignore[misc]
            last_chunk_at = time.monotonic()
    finally:
        if not pump_task.done():
            pump_task.cancel()
            try:
                await pump_task
            except asyncio.CancelledError:
                pass
        if not finished and not failed and on_cancel is not None:
            on_cancel()
