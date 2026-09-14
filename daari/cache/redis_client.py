"""Shared Redis client construction with socket timeouts (issue #463)."""

from __future__ import annotations

from typing import Any


DEFAULT_REDIS_TIMEOUT_SECONDS = 2.0


def connect_redis(
    redis_url: str,
    *,
    timeout_seconds: float = DEFAULT_REDIS_TIMEOUT_SECONDS,
    decode_responses: bool = True,
) -> Any:
    """Build a redis-py client that fails fast on hang/partition.

    ``socket_connect_timeout`` and ``socket_timeout`` default to ~2s so a
    network partition cannot stall gateway requests for the OS TCP timeout.
    """
    try:
        import redis
    except ImportError as exc:
        raise RuntimeError(
            "cache.backend=redis requires the redis package — "
            "pip install 'redis>=5' (or daari[redis])"
        ) from exc
    timeout = float(timeout_seconds) if timeout_seconds and timeout_seconds > 0 else DEFAULT_REDIS_TIMEOUT_SECONDS
    return redis.Redis.from_url(
        redis_url,
        decode_responses=decode_responses,
        socket_connect_timeout=timeout,
        socket_timeout=timeout,
    )
