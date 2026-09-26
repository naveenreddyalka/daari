"""RPM / TPM / concurrency limits with Redis or SQLite counters (issue #169).

Redis outages degrade to per-replica SQLite (or fail-open) instead of 500ing
the gateway (issue #463).
"""

from __future__ import annotations

import asyncio
import heapq
import sqlite3
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from daari.cache.redis_client import DEFAULT_REDIS_TIMEOUT_SECONDS, connect_redis

WINDOW_SECONDS = 60
# Unix epoch is UTC midnight, so a 86400s bucket is a calendar day (#717).
DAY_SECONDS = 86400
DEFAULT_PROBE_INTERVAL_SECONDS = 5.0
RATELIMIT_WARNING_HEADER = "x-daari-ratelimit-warning"

# Lower rank wakes first at the in-flight gate (#848).
PRIORITY_RANK = {"high": 0, "normal": 1, "low": 2}


def normalize_priority(value: str | None) -> str:
    text = str(value or "normal").strip().lower()
    return text if text in PRIORITY_RANK else "normal"


@dataclass(frozen=True)
class RateLimitDecision:
    allowed: bool
    limit: int
    remaining: int
    reset_epoch: int
    retry_after: int | None = None
    scope: str = ""
    backend: str = ""
    # Entity that owns the tightest counter: key | team | model | concurrency (#617).
    bucket: str = ""

    @property
    def used(self) -> int:
        if self.limit <= 0:
            return 0
        return max(0, self.limit - self.remaining)

    def in_soft_band(self, soft_ratio: float) -> bool:
        """True when usage crossed the soft line but the hard cap still allows (#518)."""
        mark = float(soft_ratio)
        if not self.allowed or mark <= 0 or mark > 1.0 or self.limit <= 0:
            return False
        return (self.used / float(self.limit)) >= mark

    def headers(self, *, soft: bool = False) -> dict[str, str]:
        if self.limit <= 0:
            return {}
        headers = {
            "X-RateLimit-Limit": str(self.limit),
            "X-RateLimit-Remaining": str(max(0, self.remaining)),
            "X-RateLimit-Reset": str(self.reset_epoch),
        }
        if self.bucket:
            headers["X-RateLimit-Scope"] = self.bucket
        if self.backend:
            headers["X-RateLimit-Backend"] = self.backend
        if self.retry_after is not None:
            headers["Retry-After"] = str(self.retry_after)
        if soft and self.allowed:
            headers[RATELIMIT_WARNING_HEADER] = "soft"
        return headers


class CounterBackend(Protocol):
    name: str

    def increment(
        self, key: str, amount: int = 1, *, window_seconds: int = WINDOW_SECONDS
    ) -> int: ...


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
                # Scope cleanup to this key so a 60s window cannot wipe an 86400s rpd row.
                conn.execute(
                    "DELETE FROM counters WHERE key = ? AND window < ?",
                    (key, window),
                )
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
        timeout_seconds: float = DEFAULT_REDIS_TIMEOUT_SECONDS,
    ) -> None:
        self.redis_url = redis_url
        self.prefix = prefix
        self.timeout_seconds = timeout_seconds
        self._client = client

    def _store(self) -> Any:
        if self._client is None:
            self._client = connect_redis(self.redis_url, timeout_seconds=self.timeout_seconds)
        return self._client

    def ping(self) -> bool:
        return bool(self._store().ping())

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
        fallback_backend: CounterBackend | None = None,
        fail_open: bool = False,
        probe_interval_seconds: float = DEFAULT_PROBE_INTERVAL_SECONDS,
    ) -> None:
        self._primary = backend
        self.backend = backend
        self._fallback = fallback_backend
        self.fail_open = fail_open
        self.default_rpm = default_rpm
        self.default_tpm = default_tpm
        self.model_rpm = model_rpm
        self.model_tpm = model_tpm
        self.max_in_flight = max_in_flight
        self.queue_size = queue_size
        self.retry_after_seconds = retry_after_seconds
        self.in_flight = 0
        self.interactive_in_flight = 0
        self.queued = 0
        self.draining = False
        self._lock = asyncio.Lock()
        # (rank, seq, Future) — lower rank wakes first; seq is FIFO within class (#848).
        self._waiters: list[tuple[int, int, asyncio.Future[bool]]] = []
        self._waiter_seq = 0
        self._interactive_lock = threading.Lock()
        self._state_lock = threading.Lock()
        self._degraded = False
        self._degraded_logged = False
        self._degrade_mode: str | None = None
        self._last_probe = 0.0
        self._probe_interval = max(0.0, float(probe_interval_seconds))

    def begin_drain(self) -> None:
        """Stop admitting new arrivals; queued waiters still wake on release (#1104)."""
        self.draining = True

    def _deny_concurrency(self) -> RateLimitDecision:
        return RateLimitDecision(
            allowed=False,
            limit=self.max_in_flight,
            remaining=0,
            reset_epoch=int(time.time()) + self.retry_after_seconds,
            retry_after=self.retry_after_seconds,
            scope="concurrency",
            backend=self.backend.name,
            bucket="concurrency",
        )

    @property
    def degraded(self) -> bool:
        with self._state_lock:
            return self._degraded

    def begin_interactive(self) -> None:
        """Count an interactive HTTP request for batch idle-yield (#444)."""
        with self._interactive_lock:
            self.interactive_in_flight += 1

    def end_interactive(self) -> None:
        with self._interactive_lock:
            self.interactive_in_flight = max(0, self.interactive_in_flight - 1)

    def interactive_load(self) -> int:
        with self._interactive_lock:
            return self.interactive_in_flight

    def probe_redis(self) -> str:
        """Return ``ok`` or the exception type name for ``/ready`` (#463)."""
        primary = self._primary
        if getattr(primary, "name", "") != "redis":
            return "ok"
        try:
            if hasattr(primary, "ping"):
                primary.ping()
            else:
                primary._store().ping()  # type: ignore[attr-defined]
            return "ok"
        except Exception as exc:
            return type(exc).__name__

    def _enter_degraded(self, exc: BaseException) -> None:
        from daari.gateway.request_log import log_gateway_event

        with self._state_lock:
            self._degraded = True
            mode = "fail_open" if self.fail_open else "sqlite_fallback"
            self._degrade_mode = mode
            if self.fail_open:
                # Keep primary as named backend for diagnostics; counting skipped.
                pass
            elif self._fallback is not None:
                self.backend = self._fallback
            should_log = not self._degraded_logged
            if should_log:
                self._degraded_logged = True
        if should_log:
            log_gateway_event(
                "rate_limit.degraded",
                {
                    "error": f"{type(exc).__name__}: {exc}",
                    "mode": mode,
                    "backend": self.backend.name,
                },
            )

    def _maybe_recover(self) -> None:
        if getattr(self._primary, "name", "") != "redis":
            return
        now = time.monotonic()
        with self._state_lock:
            if not self._degraded:
                return
            if now - self._last_probe < self._probe_interval:
                return
            self._last_probe = now
        try:
            if hasattr(self._primary, "ping"):
                self._primary.ping()  # type: ignore[attr-defined]
            else:
                self._primary._store().ping()  # type: ignore[attr-defined]
        except Exception:
            return
        from daari.gateway.request_log import log_gateway_event

        with self._state_lock:
            self.backend = self._primary
            self._degraded = False
            self._degraded_logged = False
            self._degrade_mode = None
        log_gateway_event("rate_limit.recovered", {"backend": "redis"})

    def _increment(self, key: str, amount: int, *, window_seconds: int = WINDOW_SECONDS) -> int:
        with self._state_lock:
            degraded = self._degraded
        if degraded:
            self._maybe_recover()
            with self._state_lock:
                degraded = self._degraded

        if not degraded:
            try:
                return self._primary.increment(key, amount, window_seconds=window_seconds)
            except Exception as exc:
                self._enter_degraded(exc)

        if self.fail_open:
            # Count of 0 → remaining stays at the full limit; request allowed.
            return 0

        fallback = self._fallback
        if fallback is not None:
            with self._state_lock:
                self.backend = fallback
            return fallback.increment(key, amount, window_seconds=window_seconds)
        # No fallback configured — still must not 500.
        return 0

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
        team_id: str | None = None,
        team_rpm: int | None = None,
        team_tpm: int | None = None,
        rpd: int | None = None,
        team_rpd: int | None = None,
        family: str | None = None,
        family_rpm: int | None = None,
        family_tpm: int | None = None,
    ) -> RateLimitDecision:
        key_rpm = self.default_rpm if rpm is None else rpm
        key_tpm = self.default_tpm if tpm is None else tpm
        per_model_rpm = self.model_rpm if model_rpm is None else model_rpm
        per_model_tpm = self.model_tpm if model_tpm is None else model_tpm
        if per_model_rpm <= 0:
            per_model_rpm = key_rpm
        if per_model_tpm <= 0:
            per_model_tpm = key_tpm
        agg_team_rpm = 0 if team_rpm is None else int(team_rpm)
        agg_team_tpm = 0 if team_tpm is None else int(team_tpm)
        # 0 / unset = unlimited. Separate from rpm so a minute window can stay open (#717).
        key_rpd = 0 if rpd is None else int(rpd)
        agg_team_rpd = 0 if team_rpd is None else int(team_rpd)
        fam = str(family or "").strip().lower() or None
        fam_rpm = 0 if family_rpm is None else max(0, int(family_rpm))
        fam_tpm = 0 if family_tpm is None else max(0, int(family_tpm))

        now = time.time()
        reset = (int(now // WINDOW_SECONDS) + 1) * WINDOW_SECONDS
        tightest = RateLimitDecision(
            allowed=True,
            limit=0,
            remaining=0,
            reset_epoch=reset,
            backend=self.backend.name,
        )
        # counter key, scope, bucket, amount, limit, window seconds
        checks: list[tuple[str, str, str, int, int, int]] = []
        if key_rpm > 0:
            checks.append((f"rpm:{key_id}", "rpm", "key", 1, key_rpm, WINDOW_SECONDS))
        if fam and fam_rpm > 0:
            checks.append(
                (f"rpm:{key_id}:family:{fam}", "rpm", f"family:{fam}", 1, fam_rpm, WINDOW_SECONDS)
            )
        if per_model_rpm > 0:
            checks.append(
                (f"rpm:{key_id}:{model}", "rpm", "model", 1, per_model_rpm, WINDOW_SECONDS)
            )
        if key_tpm > 0:
            checks.append((f"tpm:{key_id}", "tpm", "key", max(1, tokens), key_tpm, WINDOW_SECONDS))
        if fam and fam_tpm > 0:
            checks.append(
                (
                    f"tpm:{key_id}:family:{fam}",
                    "tpm",
                    f"family:{fam}",
                    max(1, tokens),
                    fam_tpm,
                    WINDOW_SECONDS,
                )
            )
        if per_model_tpm > 0:
            checks.append(
                (
                    f"tpm:{key_id}:{model}",
                    "tpm",
                    "model",
                    max(1, tokens),
                    per_model_tpm,
                    WINDOW_SECONDS,
                )
            )
        # Team aggregate ceilings share the same counter backend (#546).
        if team_id and agg_team_rpm > 0:
            checks.append((f"rpm:team:{team_id}", "rpm", "team", 1, agg_team_rpm, WINDOW_SECONDS))
        if team_id and agg_team_tpm > 0:
            checks.append(
                (f"tpm:team:{team_id}", "tpm", "team", max(1, tokens), agg_team_tpm, WINDOW_SECONDS)
            )
        if key_rpd > 0:
            checks.append((f"rpd:{key_id}", "rpd", "key", 1, key_rpd, DAY_SECONDS))
        if team_id and agg_team_rpd > 0:
            checks.append((f"rpd:team:{team_id}", "rpd", "team", 1, agg_team_rpd, DAY_SECONDS))

        for counter_key, scope, bucket, amount, limit, window_seconds in checks:
            count = self._increment(counter_key, amount, window_seconds=window_seconds)
            window_reset = (int(now // window_seconds) + 1) * window_seconds
            remaining = max(0, limit - count)
            denied = count > limit
            # Day caps must not advertise the 1s rpm delay (#738).
            if not denied:
                retry_after = None
            elif scope == "rpd":
                retry_after = max(1, int(window_reset - now))
            else:
                retry_after = self.retry_after_seconds
            decision = RateLimitDecision(
                allowed=not denied,
                limit=limit,
                remaining=remaining,
                reset_epoch=window_reset,
                retry_after=retry_after,
                scope=scope,
                backend=self.backend.name,
                bucket=bucket,
            )
            if tightest.limit <= 0 or remaining < tightest.remaining or not decision.allowed:
                tightest = decision
            if not decision.allowed:
                return decision
        return tightest

    def _wake_next_locked(self) -> None:
        while self._waiters and self.in_flight < self.max_in_flight:
            _rank, _seq, fut = heapq.heappop(self._waiters)
            self.queued = max(0, self.queued - 1)
            if fut.done():
                continue
            self.in_flight += 1
            fut.set_result(True)

    async def acquire(self, priority: str = "normal") -> RateLimitDecision:
        if self.max_in_flight <= 0:
            if self.draining:
                return self._deny_concurrency()
            return RateLimitDecision(
                allowed=True,
                limit=0,
                remaining=0,
                reset_epoch=int(time.time()) + self.retry_after_seconds,
                backend=self.backend.name,
                scope="concurrency",
                bucket="concurrency",
            )
        rank = PRIORITY_RANK[normalize_priority(priority)]
        async with self._lock:
            if self.draining:
                return self._deny_concurrency()
            # Free slots go to the highest-priority waiter before a new arrival.
            self._wake_next_locked()
            can_take = self.in_flight < self.max_in_flight and (
                not self._waiters or rank < self._waiters[0][0]
            )
            if can_take:
                self.in_flight += 1
                return RateLimitDecision(
                    allowed=True,
                    limit=self.max_in_flight,
                    remaining=max(0, self.max_in_flight - self.in_flight),
                    reset_epoch=int(time.time()) + self.retry_after_seconds,
                    backend=self.backend.name,
                    scope="concurrency",
                    bucket="concurrency",
                )
            if self.queued >= self.queue_size:
                return self._deny_concurrency()
            loop = asyncio.get_running_loop()
            fut: asyncio.Future[bool] = loop.create_future()
            seq = self._waiter_seq
            self._waiter_seq += 1
            heapq.heappush(self._waiters, (rank, seq, fut))
            self.queued += 1
        try:
            await fut
            return RateLimitDecision(
                allowed=True,
                limit=self.max_in_flight,
                remaining=max(0, self.max_in_flight - self.in_flight),
                reset_epoch=int(time.time()) + self.retry_after_seconds,
                backend=self.backend.name,
                scope="concurrency",
                bucket="concurrency",
            )
        except asyncio.CancelledError:
            async with self._lock:
                self._drop_waiter(fut)
            raise

    def _drop_waiter(self, fut: asyncio.Future[bool]) -> None:
        kept: list[tuple[int, int, asyncio.Future[bool]]] = []
        removed = False
        for item in self._waiters:
            if item[2] is fut and not removed:
                removed = True
                self.queued = max(0, self.queued - 1)
                continue
            kept.append(item)
        if removed:
            heapq.heapify(kept)
            self._waiters = kept
        if not fut.done():
            fut.cancel()

    async def release(self) -> None:
        if self.max_in_flight <= 0:
            return
        async with self._lock:
            self.in_flight = max(0, self.in_flight - 1)
            self._wake_next_locked()

    def team_rate_gauges(self, teams: list[Any]) -> list[dict[str, Any]]:
        """Scrape-time RPM/TPM remaining for teams with configured ceilings (#617)."""
        rows: list[dict[str, Any]] = []
        for team in teams:
            team_id = str(getattr(team, "team_id", "") or "")
            name = str(getattr(team, "name", "") or team_id or "unknown")
            if not team_id:
                continue
            rpm = int(getattr(team, "rpm", 0) or 0)
            tpm = int(getattr(team, "tpm", 0) or 0)
            if rpm > 0:
                used = int(self._increment(f"rpm:team:{team_id}", 0))
                rows.append(
                    {
                        "team": name,
                        "kind": "rpm",
                        "limit": rpm,
                        "remaining": max(0, rpm - used),
                    }
                )
            if tpm > 0:
                used = int(self._increment(f"tpm:team:{team_id}", 0))
                rows.append(
                    {
                        "team": name,
                        "kind": "tpm",
                        "limit": tpm,
                        "remaining": max(0, tpm - used),
                    }
                )
            rpd = int(getattr(team, "rpd", 0) or 0)
            if rpd > 0:
                used = int(self._increment(f"rpd:team:{team_id}", 0, window_seconds=DAY_SECONDS))
                rows.append(
                    {
                        "team": name,
                        "kind": "rpd",
                        "limit": rpd,
                        "remaining": max(0, rpd - used),
                    }
                )
        return rows

    def key_rate_gauges(self, keys: list[Any]) -> list[dict[str, Any]]:
        """Scrape-time RPD remaining for keys that opted into a day cap.

        Zero-increment read so a scrape does not consume the cap. The label is
        the key name, never the secret.
        """
        rows: list[dict[str, Any]] = []
        for key in keys:
            rpd = int(getattr(key, "rpd", 0) or 0)
            key_id = str(getattr(key, "key_id", "") or "")
            if rpd <= 0 or not key_id:
                continue
            name = str(getattr(key, "name", "") or "").strip() or key_id
            used = int(self._increment(f"rpd:{key_id}", 0, window_seconds=DAY_SECONDS))
            rows.append(
                {
                    "key": name,
                    "kind": "rpd",
                    "limit": rpd,
                    "remaining": max(0, rpd - used),
                }
            )
        return rows

    def snapshot(self) -> dict[str, Any]:
        with self._state_lock:
            degraded = self._degraded
            mode = self._degrade_mode
        return {
            "backend": self.backend.name,
            "degraded": degraded,
            "degrade_mode": mode,
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


def estimate_audio_upload_tokens(body: bytes, content_type: str) -> int | None:
    """TPM for multipart ASR: ``len(file_bytes) // 4``. None when there is no file part.

    JSON chat and embeddings stay on :func:`estimate_request_tokens`. A failed
    parse returns None so the caller keeps the one-token fallback instead of 500.
    """
    if not body or "multipart/form-data" not in (content_type or "").lower():
        return None
    from io import BytesIO

    from python_multipart.exceptions import FormParserError
    from python_multipart.multipart import parse_form

    sizes: list[int] = []
    opened: list[Any] = []

    def _on_file(uploaded: Any) -> None:
        opened.append(uploaded)
        name = getattr(uploaded, "field_name", None)
        if name in (b"file", "file"):
            sizes.append(int(getattr(uploaded, "size", 0) or 0))

    try:
        parse_form(
            {"Content-Type": content_type.encode("latin-1", errors="replace")},
            BytesIO(body),
            None,
            _on_file,
        )
    except (FormParserError, ValueError):
        return None
    finally:
        for uploaded in opened:
            close = getattr(uploaded, "close", None)
            if close is not None:
                close()
    if not sizes:
        return None
    return max(1, sum(sizes) // 4)


def request_model(payload: dict[str, Any] | None) -> str:
    if payload and isinstance(payload.get("model"), str) and payload["model"].strip():
        return payload["model"].strip()
    return "daari"


# Safe methods never carry a JSON body worth buffering for TPM (#939).
SAFE_HTTP_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


def should_buffer_body_for_rate_limit(method: str) -> bool:
    return (method or "").upper() not in SAFE_HTTP_METHODS


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
    fail_open = bool(getattr(rl, "fail_open", False))
    cache = getattr(settings, "cache", None)
    vk_path = Path(settings.server.virtual_keys.path).expanduser()
    sqlite_backend = SqliteCounterBackend(vk_path.parent / "rate-limit.sqlite3")
    if getattr(cache, "backend", "disk") == "redis":
        timeout = float(
            getattr(cache, "redis_timeout_seconds", DEFAULT_REDIS_TIMEOUT_SECONDS)
            or DEFAULT_REDIS_TIMEOUT_SECONDS
        )
        backend: CounterBackend = RedisCounterBackend(
            redis_url=getattr(cache, "redis_url", "redis://127.0.0.1:6379/0"),
            prefix="daari:rl:",
            client=redis_client,
            timeout_seconds=timeout,
        )
        fallback: CounterBackend | None = sqlite_backend
    else:
        backend = sqlite_backend
        fallback = None
    return RateLimiter(
        backend,
        default_rpm=default_rpm,
        default_tpm=default_tpm,
        model_rpm=model_rpm,
        model_tpm=model_tpm,
        max_in_flight=max_in_flight,
        queue_size=queue_size,
        retry_after_seconds=retry_after,
        fallback_backend=fallback,
        fail_open=fail_open,
    )
