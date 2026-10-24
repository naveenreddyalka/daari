"""Fleet-shared circuit-breaker open/reject state via Redis (#1868 / #1908).

Key prefixes (document for operators):

- ``daari:breaker:{share_key}`` — open snapshot JSON (TTL = cooldown + pad)
- ``daari:breaker_rejects:{share_key}`` — reject counter while open
- ``daari:systemone:breaker:`` / ``daari:systemone:breaker_rejects:`` —
  systemone-specific prefixes (unchanged; see ``daari.gateway.systemone``)

``share_key`` for pool breakers: ``frontier:{id}``, ``local:{id}``, ``mcp:{id}``.
Redis errors fail open to process-local breaker state.
"""

from __future__ import annotations

import json
import time
from typing import Any

from daari.gateway.request_log import log_gateway_event

_breaker_redis: Any | None = None
_BREAKER_REDIS_PREFIX = "daari:breaker:"
_BREAKER_REJECTS_REDIS_PREFIX = "daari:breaker_rejects:"
_BREAKER_REDIS_TTL_PAD = 30


def set_breaker_redis(client: Any | None) -> None:
    """Install (or clear) the shared pool-breaker Redis client."""
    global _breaker_redis
    _breaker_redis = client


def breaker_redis_client() -> Any | None:
    return _breaker_redis


def breaker_redis_backend() -> str:
    return "redis" if _breaker_redis is not None else "local"


def share_key_for(family: str, identity: str) -> str:
    """Build a stable share key: ``frontier:openai``, ``local:gpu-a``, ``mcp:tools``."""
    fam = str(family or "").strip().lower() or "pool"
    ident = str(identity or "").strip() or "default"
    return f"{fam}:{ident}"


def configure_breaker_redis_store(settings: Any) -> None:
    """Wire Redis-shared breaker state when ``cache.backend=redis`` (#1908)."""
    cache = getattr(settings, "cache", None)
    if getattr(cache, "backend", "disk") != "redis":
        set_breaker_redis(None)
        return
    url = str(getattr(cache, "redis_url", "") or "").strip()
    if not url:
        set_breaker_redis(None)
        return
    try:
        from daari.cache.redis_client import connect_redis

        timeout = float(getattr(cache, "redis_timeout_seconds", 2.0) or 2.0)
        set_breaker_redis(connect_redis(url, timeout_seconds=timeout))
    except Exception:
        log_gateway_event("pool_breaker_redis_error", {"op": "connect"})
        set_breaker_redis(None)


def _state_key(share_key: str) -> str:
    return f"{_BREAKER_REDIS_PREFIX}{share_key}"


def _rejects_key(share_key: str) -> str:
    return f"{_BREAKER_REJECTS_REDIS_PREFIX}{share_key}"


def _redis_decode(raw: Any) -> str | None:
    if raw is None:
        return None
    if isinstance(raw, bytes):
        return raw.decode("utf-8", errors="replace")
    return str(raw)


def load_shared_open(share_key: str, *, cooldown_seconds: float) -> bool | None:
    """Return True/False when Redis answers; None on miss-config or error (fail-open)."""
    if _breaker_redis is None or not share_key:
        return None
    try:
        raw = _redis_decode(_breaker_redis.get(_state_key(share_key)))
        if not raw:
            return False
        data = json.loads(raw)
        opened_at = float(data.get("opened_at") or 0.0)
        cooldown = float(data.get("cooldown_seconds") or cooldown_seconds or 30.0)
        if opened_at <= 0:
            return False
        return (time.time() - opened_at) < cooldown
    except Exception:
        log_gateway_event(
            "pool_breaker_redis_error", {"op": "get", "share_key": share_key}
        )
        return None


def publish_shared_open(
    share_key: str, *, cooldown_seconds: float, failures: int
) -> None:
    if _breaker_redis is None or not share_key:
        return
    try:
        cooldown = max(1.0, float(cooldown_seconds or 30.0))
        payload = json.dumps(
            {
                "state": "open",
                "opened_at": time.time(),
                "cooldown_seconds": cooldown,
                "failures": int(failures),
            }
        )
        _breaker_redis.set(
            _state_key(share_key),
            payload,
            ex=int(cooldown) + _BREAKER_REDIS_TTL_PAD,
        )
    except Exception:
        log_gateway_event(
            "pool_breaker_redis_error", {"op": "set", "share_key": share_key}
        )


def clear_shared_breaker(share_key: str | None = None) -> None:
    if _breaker_redis is None:
        return
    try:
        if share_key is not None:
            _breaker_redis.delete(_state_key(share_key), _rejects_key(share_key))
            return
        state_keys = list(_breaker_redis.keys(f"{_BREAKER_REDIS_PREFIX}*") or [])
        reject_keys = list(
            _breaker_redis.keys(f"{_BREAKER_REJECTS_REDIS_PREFIX}*") or []
        )
        keys = [str(k) for k in state_keys + reject_keys]
        if keys:
            _breaker_redis.delete(*keys)
    except Exception:
        log_gateway_event(
            "pool_breaker_redis_error",
            {"op": "delete", "share_key": share_key or "*"},
        )


def incr_shared_rejects(share_key: str, *, cooldown_seconds: float) -> int | None:
    if _breaker_redis is None or not share_key:
        return None
    try:
        key = _rejects_key(share_key)
        count = int(_breaker_redis.incr(key))
        if count == 1:
            cooldown = max(1.0, float(cooldown_seconds or 30.0))
            _breaker_redis.expire(key, int(cooldown) + _BREAKER_REDIS_TTL_PAD)
        return count
    except Exception:
        log_gateway_event(
            "pool_breaker_redis_error", {"op": "incr", "share_key": share_key}
        )
        return None


def load_shared_rejects(share_key: str) -> int | None:
    if _breaker_redis is None or not share_key:
        return None
    try:
        raw = _redis_decode(_breaker_redis.get(_rejects_key(share_key)))
        if raw is None:
            return 0
        return int(raw)
    except Exception:
        log_gateway_event(
            "pool_breaker_redis_error",
            {"op": "get_rejects", "share_key": share_key},
        )
        return None
