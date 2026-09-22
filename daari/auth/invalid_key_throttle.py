"""Throttle invalid API-key attempts by client IP (#935).

After ``auth.max_failures`` 401s in ``auth.window_seconds`` from one IP,
subsequent auth attempts return 429 + Retry-After with exponential backoff.
Redis-backed when ``cache.backend=redis``; in-process otherwise. Redis errors
fail open so a counter outage never locks operators out.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any

from daari.gateway.request_log import log_gateway_event

DEFAULT_MAX_FAILURES = 10
DEFAULT_WINDOW_SECONDS = 60.0
DEFAULT_BASE_BACKOFF_SECONDS = 1
LOOPBACK = frozenset({"127.0.0.1", "::1", "localhost", "0:0:0:0:0:0:0:1", "testclient"})


@dataclass
class AuthThrottleDecision:
    allowed: bool
    retry_after: int = 0
    failures: int = 0


@dataclass
class AuthThrottle:
    max_failures: int = DEFAULT_MAX_FAILURES
    window_seconds: float = DEFAULT_WINDOW_SECONDS
    base_backoff_seconds: int = DEFAULT_BASE_BACKOFF_SECONDS
    enabled: bool = True
    exempt_loopback: bool = True
    redis: Any | None = None
    redis_key_prefix: str = "daari:auth_fail:"
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
    _hits: dict[str, list[float]] = field(default_factory=dict, repr=False)

    def _is_loopback(self, client_ip: str) -> bool:
        host = (client_ip or "").strip().lower().strip("[]")
        return host in LOOPBACK or host.startswith("127.")

    def _prune(self, stamps: list[float], now: float) -> list[float]:
        cutoff = now - self.window_seconds
        return [t for t in stamps if t >= cutoff]

    def _backoff(self, failures: int) -> int:
        # Exponential: base * 2^(overage-1), capped at window.
        over = max(1, failures - self.max_failures + 1)
        return min(int(self.window_seconds), self.base_backoff_seconds * (2 ** (over - 1)))

    def check(self, client_ip: str, *, now: float | None = None) -> AuthThrottleDecision:
        if not self.enabled or self.max_failures <= 0:
            return AuthThrottleDecision(allowed=True)
        ip = (client_ip or "").strip() or "unknown"
        if self.exempt_loopback and self._is_loopback(ip):
            return AuthThrottleDecision(allowed=True)
        moment = time.monotonic() if now is None else now
        failures = self._count(ip, moment)
        if failures >= self.max_failures:
            return AuthThrottleDecision(
                allowed=False,
                retry_after=self._backoff(failures),
                failures=failures,
            )
        return AuthThrottleDecision(allowed=True, failures=failures)

    def record_failure(self, client_ip: str, *, now: float | None = None) -> int:
        if not self.enabled or self.max_failures <= 0:
            return 0
        ip = (client_ip or "").strip() or "unknown"
        if self.exempt_loopback and self._is_loopback(ip):
            return 0
        moment = time.monotonic() if now is None else now
        return self._add(ip, moment)

    def _redis_key(self, ip: str) -> str:
        return f"{self.redis_key_prefix}{ip}"

    def _count(self, ip: str, now: float) -> int:
        if self.redis is not None:
            try:
                raw = self.redis.get(self._redis_key(ip))
                return int(raw or 0)
            except Exception:
                log_gateway_event("auth_throttle_redis_error", {"op": "get", "ip": ip[:64]})
                # fail open — fall through to local view
        with self._lock:
            stamps = self._prune(self._hits.get(ip, []), now)
            self._hits[ip] = stamps
            return len(stamps)

    def _add(self, ip: str, now: float) -> int:
        if self.redis is not None:
            try:
                key = self._redis_key(ip)
                count = int(self.redis.incr(key))
                if count == 1:
                    self.redis.expire(key, int(max(1, self.window_seconds)))
                return count
            except Exception:
                log_gateway_event("auth_throttle_redis_error", {"op": "incr", "ip": ip[:64]})
        with self._lock:
            stamps = self._prune(self._hits.get(ip, []), now)
            stamps.append(now)
            self._hits[ip] = stamps
            return len(stamps)


def client_ip_from_request(request: Any) -> str:
    """Best-effort client IP; prefer direct peer (ignore spoofable XFF by default)."""
    client = getattr(request, "client", None)
    if client is not None and getattr(client, "host", None):
        return str(client.host)
    return "unknown"


def build_auth_throttle(settings: Any) -> AuthThrottle:
    auth = getattr(settings, "auth", None)
    max_failures = int(getattr(auth, "max_failures", DEFAULT_MAX_FAILURES) or 0)
    window = float(getattr(auth, "window_seconds", DEFAULT_WINDOW_SECONDS) or DEFAULT_WINDOW_SECONDS)
    enabled = bool(getattr(auth, "throttle_enabled", True))
    exempt = bool(getattr(auth, "exempt_loopback", True))
    redis_client = None
    cache = getattr(settings, "cache", None)
    if getattr(cache, "backend", "disk") == "redis":
        url = str(getattr(cache, "redis_url", "") or "").strip()
        if url:
            try:
                from daari.cache.redis_client import connect_redis

                timeout = float(getattr(cache, "redis_timeout_seconds", 2.0) or 2.0)
                redis_client = connect_redis(url, timeout_seconds=timeout)
            except Exception:
                log_gateway_event("auth_throttle_redis_error", {"op": "connect"})
                redis_client = None
    return AuthThrottle(
        max_failures=max_failures,
        window_seconds=window,
        enabled=enabled,
        exempt_loopback=exempt,
        redis=redis_client,
    )
