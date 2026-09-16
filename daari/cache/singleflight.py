"""In-process singleflight for L0 exact-cache fills (#499).

Concurrent identical cold misses share one upstream execution; waiters await
the leader's result. Errors clear the in-flight slot so the next attempt can
retry (no permanent poison).
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import TypeVar

T = TypeVar("T")


class SingleFlight:
    """Coalesce concurrent `do(key, fill)` calls for the same key."""

    def __init__(self) -> None:
        self._inflight: dict[str, asyncio.Future] = {}

    async def do(self, key: str, fill: Callable[[], Awaitable[T]]) -> T:
        existing = self._inflight.get(key)
        if existing is not None:
            return await existing  # type: ignore[no-any-return]

        loop = asyncio.get_running_loop()
        fut: asyncio.Future = loop.create_future()
        self._inflight[key] = fut
        try:
            result = await fill()
        except BaseException as exc:
            if not fut.done():
                fut.set_exception(exc)
            raise
        else:
            if not fut.done():
                fut.set_result(result)
            return result
        finally:
            if self._inflight.get(key) is fut:
                del self._inflight[key]
