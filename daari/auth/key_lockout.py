"""Per-key soft lockout for invalid-auth storms (#1684).

Independent of the per-IP throttle. After ``auth.key_lockout.max_failures``
invalid attempts for the same key prefix inside ``window_seconds``, further
attempts for that prefix return 429 for ``lockout_seconds``. Redis-backed when
``cache.backend=redis``; in-process otherwise. Redis errors fail open.
"""

from __future__ import annotations

import math
import threading
import time
from dataclasses import dataclass, field
from typing import Any

from daari.enterprise.audit import key_prefix_for_audit
from daari.gateway.request_log import log_gateway_event

DEFAULT_MAX_FAILURES = 10
DEFAULT_WINDOW_SECONDS = 60.0
DEFAULT_LOCKOUT_SECONDS = 60


@dataclass
class KeyLockoutDecision:
    allowed: bool
    retry_after: int = 0
    failures: int = 0
    prefix: str = ""


@dataclass
class KeyLockout:
    max_failures: int = DEFAULT_MAX_FAILURES
    window_seconds: float = DEFAULT_WINDOW_SECONDS
    lockout_seconds: int = DEFAULT_LOCKOUT_SECONDS
    enabled: bool = True
    exempt_loopback: bool = True
    redis: Any | None = None
    redis_key_prefix: str = "daari:auth_key_fail:"
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
    _hits: dict[str, list[float]] = field(default_factory=dict, repr=False)
    _locked_until: dict[str, float] = field(default_factory=dict, repr=False)

    def subject(self, supplied: str | None) -> str:
        return key_prefix_for_audit(supplied) or "anonymous"

    def _is_loopback(self, client_ip: str) -> bool:
        from daari.auth.invalid_key_throttle import LOOPBACK

        host = (client_ip or "").strip().lower().strip("[]")
        return host in LOOPBACK or host.startswith("127.")

    def _skip(self, client_ip: str) -> bool:
        if not self.enabled or self.max_failures <= 0:
            return True
        if self.exempt_loopback and self._is_loopback(client_ip):
            return True
        return False

    def _prune(self, stamps: list[float], now: float) -> list[float]:
        cutoff = now - self.window_seconds
        return [t for t in stamps if t >= cutoff]

    def check(
        self,
        supplied: str | None,
        *,
        client_ip: str = "",
        now: float | None = None,
    ) -> KeyLockoutDecision:
        prefix = self.subject(supplied)
        if self._skip(client_ip):
            return KeyLockoutDecision(allowed=True, prefix=prefix)
        moment = time.monotonic() if now is None else now
        if self.redis is not None:
            try:
                lock_key = self._lock_key(prefix)
                if self.redis.get(lock_key):
                    return KeyLockoutDecision(
                        allowed=False,
                        retry_after=self._redis_retry(lock_key),
                        failures=self.max_failures,
                        prefix=prefix,
                    )
                raw = self.redis.get(self._count_key(prefix))
                failures = int(raw or 0)
                if failures >= self.max_failures:
                    return KeyLockoutDecision(
                        allowed=False,
                        retry_after=max(1, int(self.lockout_seconds)),
                        failures=failures,
                        prefix=prefix,
                    )
                return KeyLockoutDecision(allowed=True, failures=failures, prefix=prefix)
            except Exception:
                log_gateway_event(
                    "auth_key_lockout_redis_error", {"op": "get", "prefix": prefix}
                )
        with self._lock:
            until = self._locked_until.get(prefix, 0.0)
            if until > moment:
                return KeyLockoutDecision(
                    allowed=False,
                    retry_after=max(1, math.ceil(until - moment)),
                    failures=self.max_failures,
                    prefix=prefix,
                )
            stamps = self._prune(self._hits.get(prefix, []), moment)
            self._hits[prefix] = stamps
            failures = len(stamps)
        if failures >= self.max_failures:
            return KeyLockoutDecision(
                allowed=False,
                retry_after=max(1, int(self.lockout_seconds)),
                failures=failures,
                prefix=prefix,
            )
        return KeyLockoutDecision(allowed=True, failures=failures, prefix=prefix)

    def record_failure(
        self,
        supplied: str | None,
        *,
        client_ip: str = "",
        now: float | None = None,
    ) -> int:
        if self._skip(client_ip):
            return 0
        prefix = self.subject(supplied)
        moment = time.monotonic() if now is None else now
        if self.redis is not None:
            try:
                key = self._count_key(prefix)
                count = int(self.redis.incr(key))
                if count == 1:
                    self.redis.expire(key, int(max(1, self.window_seconds)))
                if count >= self.max_failures:
                    self.redis.set(
                        self._lock_key(prefix),
                        "1",
                        ex=max(1, int(self.lockout_seconds)),
                    )
                return count
            except Exception:
                log_gateway_event(
                    "auth_key_lockout_redis_error", {"op": "incr", "prefix": prefix}
                )
        with self._lock:
            stamps = self._prune(self._hits.get(prefix, []), moment)
            stamps.append(moment)
            self._hits[prefix] = stamps
            count = len(stamps)
            if count >= self.max_failures:
                self._locked_until[prefix] = moment + max(1, int(self.lockout_seconds))
            return count

    def _count_key(self, prefix: str) -> str:
        return f"{self.redis_key_prefix}{prefix}"

    def _lock_key(self, prefix: str) -> str:
        return f"{self.redis_key_prefix}lock:{prefix}"

    def _redis_retry(self, lock_key: str) -> int:
        ttl = getattr(self.redis, "ttl", None)
        if callable(ttl):
            try:
                raw = int(ttl(lock_key))
                if raw > 0:
                    return raw
            except Exception:
                log_gateway_event("auth_key_lockout_redis_error", {"op": "ttl"})
        return max(1, int(self.lockout_seconds))


def build_key_lockout(settings: Any) -> KeyLockout:
    auth = getattr(settings, "auth", None)
    block = getattr(auth, "key_lockout", None)
    max_failures = int(getattr(block, "max_failures", DEFAULT_MAX_FAILURES) or 0)
    window = float(getattr(block, "window_seconds", DEFAULT_WINDOW_SECONDS) or DEFAULT_WINDOW_SECONDS)
    lockout = int(getattr(block, "lockout_seconds", DEFAULT_LOCKOUT_SECONDS) or DEFAULT_LOCKOUT_SECONDS)
    enabled = bool(getattr(block, "enabled", True))
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
                log_gateway_event("auth_key_lockout_redis_error", {"op": "connect"})
                redis_client = None
    return KeyLockout(
        max_failures=max_failures,
        window_seconds=window,
        lockout_seconds=lockout,
        enabled=enabled,
        exempt_loopback=exempt,
        redis=redis_client,
    )
