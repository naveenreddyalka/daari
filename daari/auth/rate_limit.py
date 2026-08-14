"""RPM / TPM / concurrency limits with Redis or SQLite counters (issue #169)."""

from __future__ import annotations

import asyncio
import sqlite3
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

WINDOW_SECONDS = 60


@dataclass(frozen=True)
class RateLimitDecision:
    allowed: bool
    limit: int
    remaining: int
    reset_epoch: int
    retry_after: int | None = None
    scope: str = ""
    backend: str = ""

    def headers(self) -> dict[str, str]:
        if self.limit <= 0:
            return {}
        headers = {
            "X-RateLimit-Limit": str(self.limit),
            "X-RateLimit-Remaining": str(max(0, self.remaining)),
            "X-RateLimit-Reset": str(self.reset_epoch),
        }
        if self.retry_after is not None:
            headers["Retry-After"] = str(self.retry_after)
        return headers


class CounterBackend(Protocol):
    name: str

    def increment(self, key: str, amount: int = 1, *, window_seconds: int = WINDOW_SECONDS) -> int: ...


class MemoryCounterBackend:
    name = "memory"

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._counts: dict[str, tuple[int, int]] = {}

    def increment(self, key: str, amount: int = 1, *, window_seconds: int = WINDOW_SECONDS) -> int:
        window = int(time.time() // window_seconds)
        with self._lock:
            count, stored_window = self._counts.get(key, (0, window))
            if stored_window != window:
                count = 0
            count += amount
            self._counts[key] = (count, window)
            return count


class SqliteCounterBackend:
    name = "sqlite"

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path).expanduser()
        self._lock = threading.Lock()
        self._ready = False

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path, timeout=5.0)

    def _ensure(self) -> None:
        if self._ready:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS counters ("
                " key TEXT NOT NULL, window INTEGER NOT NULL, count INTEGER NOT NULL,"
                " PRIMARY KEY (key, window))"
            )
        self._ready = True

    def increment(self, key: str, amount: int = 1, *, window_seconds: int = WINDOW_SECONDS) -> int:
        window = int(time.time() // window_seconds)
        with self._lock:
            self._ensure()
            with self._connect() as conn:
                conn.execute("DELETE FROM counters WHERE window < ?", (window,))
                conn.execute(
                    "INSERT INTO counters (key, window, count) VALUES (?, ?, ?)"
                    " ON CONFLICT(key, window) DO UPDATE SET count = count + ?",
                    (key, window, amount, amount),
                )
                row = conn.execute(
                    "SELECT count FROM counters WHERE key = ? AND window = ?",
                    (key, window),
                ).fetchone()
                return int(row[0]) if row else amount


class RedisCounterBackend:
    name = "redis"

    def __init__(
        self,
        redis_url: str = "redis://127.0.0.1:6379/0",
        *,
        prefix: str = "daari:rl:",
        client: Any | None = None,
    ) -> None:
        self.redis_url = redis_url
        self.prefix = prefix
        self._client = client

    def _store(self) -> Any:
        if self._client is None:
            try:
                import redis
            except ImportError as exc:
                raise RuntimeError(
                    "cache.backend=redis requires the redis package — "
                    "pip install 'redis>=5' (or daari[redis])"
                ) from exc
            self._client = redis.Redis.from_url(self.redis_url, decode_responses=True)
        return self._client

    def increment(self, key: str, amount: int = 1, *, window_seconds: int = WINDOW_SECONDS) -> int:
        window = int(time.time() // window_seconds)
        full = f"{self.prefix}{key}:{window}"
        client = self._store()
        pipe = client.pipeline()
        pipe.incrby(full, amount)
        pipe.expire(full, window_seconds)
        results = pipe.execute()
        return int(results[0])


class RateLimiter:
    def __init__(
        self,
        backend: CounterBackend,
        *,
        default_rpm: int = 0,
        default_tpm: int = 0,
        model_rpm: int = 0,
        model_tpm: int = 0,
        max_in_flight: int = 0,
        queue_size: int = 32,
        retry_after_seconds: int = 1,
    ) -> None:
        self.backend = backend
        self.default_rpm = default_rpm
        self.default_tpm = default_tpm
        self.model_rpm = model_rpm
        self.model_tpm = model_tpm
        self.max_in_flight = max_in_flight
        self.queue_size = queue_size
        self.retry_after_seconds = retry_after_seconds
        self.in_flight = 0
        self.queued = 0
        self._cond = asyncio.Condition()

    def check(
        self,
        *,
        key_id: str,
        model: str,
        tokens: int,
        rpm: int | None = None,
        tpm: int | None = None,
        model_rpm: int | None = None,
        model_tpm: int | None = None,
    ) -> RateLimitDecision:
        key_rpm = self.default_rpm if rpm is None else rpm
        key_tpm = self.default_tpm if tpm is None else tpm
        per_model_rpm = self.model_rpm if model_rpm is None else model_rpm
        per_model_tpm = self.model_tpm if model_tpm is None else model_tpm
        if per_model_rpm <= 0:
            per_model_rpm = key_rpm
        if per_model_tpm <= 0:
            per_model_tpm = key_tpm

        reset = (int(time.time() // WINDOW_SECONDS) + 1) * WINDOW_SECONDS
        tightest = RateLimitDecision(
            allowed=True,
            limit=0,
            remaining=0,
            reset_epoch=reset,
            backend=self.backend.name,
        )
        checks: list[tuple[str, str, int, int]] = []
        if key_rpm > 0:
            checks.append((f"rpm:{key_id}", "rpm", 1, key_rpm))
        if per_model_rpm > 0:
            checks.append((f"rpm:{key_id}:{model}", "rpm", 1, per_model_rpm))
        if key_tpm > 0:
            checks.append((f"tpm:{key_id}", "tpm", max(1, tokens), key_tpm))
        if per_model_tpm > 0:
            checks.append((f"tpm:{key_id}:{model}", "tpm", max(1, tokens), per_model_tpm))

        for counter_key, scope, amount, limit in checks:
            count = self.backend.increment(counter_key, amount)
            remaining = max(0, limit - count)
            decision = RateLimitDecision(
                allowed=count <= limit,
                limit=limit,
                remaining=remaining,
                reset_epoch=reset,
                retry_after=None if count <= limit else self.retry_after_seconds,
                scope=scope,
                backend=self.backend.name,
            )
            if tightest.limit <= 0 or remaining < tightest.remaining or not decision.allowed:
                tightest = decision
            if not decision.allowed:
                return decision
        return tightest

    async def acquire(self) -> RateLimitDecision:
        if self.max_in_flight <= 0:
            return RateLimitDecision(
                allowed=True,
                limit=0,
                remaining=0,
                reset_epoch=int(time.time()) + self.retry_after_seconds,
                backend=self.backend.name,
                scope="concurrency",
            )
        async with self._cond:
            if self.in_flight < self.max_in_flight:
                self.in_flight += 1
                return RateLimitDecision(
                    allowed=True,
                    limit=self.max_in_flight,
                    remaining=max(0, self.max_in_flight - self.in_flight),
                    reset_epoch=int(time.time()) + self.retry_after_seconds,
                    backend=self.backend.name,
                    scope="concurrency",
                )
            if self.queued >= self.queue_size:
                return RateLimitDecision(
                    allowed=False,
                    limit=self.max_in_flight,
                    remaining=0,
                    reset_epoch=int(time.time()) + self.retry_after_seconds,
                    retry_after=self.retry_after_seconds,
                    scope="concurrency",
                    backend=self.backend.name,
                )
            self.queued += 1
            try:
                while self.in_flight >= self.max_in_flight:
                    await self._cond.wait()
                self.in_flight += 1
                return RateLimitDecision(
                    allowed=True,
                    limit=self.max_in_flight,
                    remaining=max(0, self.max_in_flight - self.in_flight),
                    reset_epoch=int(time.time()) + self.retry_after_seconds,
                    backend=self.backend.name,
                    scope="concurrency",
                )
            finally:
                self.queued -= 1

    async def release(self) -> None:
        if self.max_in_flight <= 0:
            return
        async with self._cond:
            self.in_flight = max(0, self.in_flight - 1)
            self._cond.notify()

    def snapshot(self) -> dict[str, Any]:
        return {
            "backend": self.backend.name,
            "rpm_limit": self.default_rpm,
            "tpm_limit": self.default_tpm,
            "in_flight": self.in_flight,
            "in_flight_max": self.max_in_flight,
            "queued": self.queued,
            "queue_size": self.queue_size,
        }


def estimate_request_tokens(payload: dict[str, Any] | None) -> int:
    if not payload:
        return 1
    chars = 0
    incoming = payload.get("input")
    if isinstance(incoming, str):
        chars += len(incoming)
    elif isinstance(incoming, list):
        chars += len(str(incoming))
    for message in payload.get("messages") or []:
        if isinstance(message, dict):
            chars += len(str(message.get("content") or ""))
    return max(1, chars // 4)


def request_model(payload: dict[str, Any] | None) -> str:
    if payload and isinstance(payload.get("model"), str) and payload["model"].strip():
        return payload["model"].strip()
    return "daari"


def build_rate_limiter(settings: Any, redis_client: Any | None = None) -> RateLimiter:
    rl = getattr(settings, "rate_limit", None)
    default_rpm = int(getattr(rl, "rpm", 0) or 0)
    default_tpm = int(getattr(rl, "tpm", 0) or 0)
    model_rpm = int(getattr(rl, "model_rpm", 0) or 0)
    model_tpm = int(getattr(rl, "model_tpm", 0) or 0)
    max_in_flight = int(getattr(rl, "max_in_flight", 0) or 0)
    raw_queue = getattr(rl, "queue_size", 32)
    queue_size = 32 if raw_queue is None else int(raw_queue)
    retry_after = int(getattr(rl, "retry_after_seconds", 1) or 1)
    cache = getattr(settings, "cache", None)
    if getattr(cache, "backend", "disk") == "redis":
        backend: CounterBackend = RedisCounterBackend(
            redis_url=getattr(cache, "redis_url", "redis://127.0.0.1:6379/0"),
            prefix="daari:rl:",
            client=redis_client,
        )
    else:
        vk_path = Path(settings.server.virtual_keys.path).expanduser()
        backend = SqliteCounterBackend(vk_path.parent / "rate-limit.sqlite3")
    return RateLimiter(
        backend,
        default_rpm=default_rpm,
        default_tpm=default_tpm,
        model_rpm=model_rpm,
        model_tpm=model_tpm,
        max_in_flight=max_in_flight,
        queue_size=queue_size,
        retry_after_seconds=retry_after,
    )
