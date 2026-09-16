"""In-process singleflight for L0 exact-cache and L1 embed-key fills
(#499, #506, #517).

Concurrent identical cold misses share one upstream execution; waiters await
the leader's result. Errors clear the in-flight slot so the next attempt can
retry (no permanent poison). Stream and non-stream share the same map. Ask
path with L1 enabled also coalesces near-identical embeds under one key.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

T = TypeVar("T")


class SingleFlight:
    """Coalesce concurrent fills for the same key (async leader + waiters)."""

    def __init__(self) -> None:
        self._inflight: dict[str, asyncio.Future] = {}

    def begin(self, key: str) -> tuple[asyncio.Future, bool]:
        """Claim leadership or join an in-flight fill.

        Returns ``(future, is_leader)``. Leaders must call ``finish``;
        waiters ``await`` the future.
        """
        existing = self._inflight.get(key)
        if existing is not None:
            return existing, False
        loop = asyncio.get_running_loop()
        fut: asyncio.Future = loop.create_future()
        self._inflight[key] = fut
        return fut, True

    def finish(
        self,
        key: str,
        fut: asyncio.Future,
        *,
        result: Any = None,
        exc: BaseException | None = None,
    ) -> None:
        """Complete a leader's future and drop the in-flight slot."""
        try:
            if not fut.done():
                if exc is not None:
                    fut.set_exception(exc)
                else:
                    fut.set_result(result)
        finally:
            if self._inflight.get(key) is fut:
                del self._inflight[key]

    async def do(self, key: str, fill: Callable[[], Awaitable[T]]) -> T:
        fut, is_leader = self.begin(key)
        if not is_leader:
            return await fut  # type: ignore[no-any-return]
        try:
            result = await fill()
        except BaseException as exc:
            self.finish(key, fut, exc=exc)
            raise
        else:
            self.finish(key, fut, result=result)
            return result
