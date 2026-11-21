"""Session pins so an agent loop stays on the model that planned the task.

Default off. A continuation (tool results after an assistant tool-call, or the
same user-turn prefix) replays the prior tier. A new human turn re-routes.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from typing import Any, Callable

from daari.gateway.internal import Message


@dataclass(frozen=True)
class SessionPin:
    tier: str
    model: str | None
    prefix_hash: str
    expires_at: float


class SessionPinStore:
    """Prefix-scoped pins so shared session/user keys do not clobber siblings (#2267)."""

    def __init__(
        self,
        ttl_seconds: float = 1800.0,
        *,
        clock: Callable[[], float] | None = None,
        redis_client: Any | None = None,
        redis_prefix: str = "daari:session-pin:",
        redis_url: str | None = None,
        redis_timeout_seconds: float = 2.0,
    ) -> None:
        self.ttl_seconds = max(0.0, float(ttl_seconds))
        self._clock = clock or time.monotonic
        # session/user key → {prefix_hash: SessionPin}
        self._pins: dict[str, dict[str, SessionPin]] = {}
        self._redis = redis_client
        self._redis_url = redis_url
        self._redis_timeout_seconds = redis_timeout_seconds
        self._redis_prefix = redis_prefix
        self._degraded = False

    def _client(self) -> Any | None:
        if self._redis is not None:
            return self._redis
        if not self._redis_url:
            return None
        from daari.cache.redis_client import connect_redis

        self._redis = connect_redis(
            self._redis_url, timeout_seconds=self._redis_timeout_seconds
        )
        return self._redis

    def _redis_key(self, key: str) -> str:
        return f"{self._redis_prefix}{key}"

    def _mark_degraded(self, exc: BaseException) -> None:
        if self._degraded:
            return
        self._degraded = True
        try:
            from daari.gateway.request_log import log_gateway_event

            log_gateway_event(
                "session_affinity.degraded",
                detail=str(exc),
                backend="redis",
            )
        except Exception:
            pass

    def _pin_live(self, pin: SessionPin) -> bool:
        if self.ttl_seconds > 0 and self._clock() >= pin.expires_at:
            return False
        return True

    def _parse_bucket(self, data: Any) -> dict[str, SessionPin]:
        """Accept legacy single-pin JSON or the prefix-scoped map."""
        if not isinstance(data, dict):
            return {}
        if "pins" in data and isinstance(data["pins"], dict):
            bucket: dict[str, SessionPin] = {}
            for prefix, row in data["pins"].items():
                if not isinstance(row, dict):
                    continue
                bucket[str(prefix)] = SessionPin(
                    tier=str(row["tier"]),
                    model=row.get("model"),
                    prefix_hash=str(row.get("prefix_hash") or prefix),
                    expires_at=float(row.get("expires_at") or 0.0),
                )
            return bucket
        if "tier" in data:
            prefix = str(data.get("prefix_hash") or "")
            return {
                prefix: SessionPin(
                    tier=str(data["tier"]),
                    model=data.get("model"),
                    prefix_hash=prefix,
                    expires_at=float(data.get("expires_at") or 0.0),
                )
            }
        return {}

    def _dump_bucket(self, bucket: dict[str, SessionPin]) -> str:
        return json.dumps(
            {
                "pins": {
                    prefix: {
                        "tier": pin.tier,
                        "model": pin.model,
                        "prefix_hash": pin.prefix_hash,
                        "expires_at": pin.expires_at,
                    }
                    for prefix, pin in bucket.items()
                }
            }
        )

    def _load_redis_bucket(self, key: str) -> dict[str, SessionPin] | None:
        client = None
        try:
            client = self._client()
        except Exception as exc:
            self._mark_degraded(exc)
            return None
        if client is None:
            return None
        try:
            raw = client.get(self._redis_key(key))
            if raw is None:
                return {}
            if isinstance(raw, bytes):
                raw = raw.decode()
            return self._parse_bucket(json.loads(raw))
        except Exception as exc:
            self._mark_degraded(exc)
            return None

    def _save_redis_bucket(self, key: str, bucket: dict[str, SessionPin]) -> bool:
        client = None
        try:
            client = self._client()
        except Exception as exc:
            self._mark_degraded(exc)
            return False
        if client is None:
            return False
        try:
            payload = self._dump_bucket(bucket)
            redis_key = self._redis_key(key)
            if self.ttl_seconds > 0:
                client.set(redis_key, payload, ex=int(max(1, self.ttl_seconds)))
            else:
                client.set(redis_key, payload)
            return True
        except Exception as exc:
            self._mark_degraded(exc)
            return False

    def _memory_bucket(self, key: str) -> dict[str, SessionPin]:
        bucket = self._pins.get(key)
        if not bucket:
            return {}
        live = {prefix: pin for prefix, pin in bucket.items() if self._pin_live(pin)}
        if not live:
            self._pins.pop(key, None)
            return {}
        if len(live) != len(bucket):
            self._pins[key] = live
        return live

    def get(self, key: str, *, prefix_hash: str | None = None) -> SessionPin | None:
        bucket = self._load_redis_bucket(key)
        if bucket is None:
            bucket = self._memory_bucket(key)
        else:
            bucket = {prefix: pin for prefix, pin in bucket.items() if self._pin_live(pin)}
        if not bucket:
            return None
        if prefix_hash is not None:
            return bucket.get(prefix_hash)
        if len(bucket) == 1:
            return next(iter(bucket.values()))
        return None

    def mismatched_pin(self, key: str, prefix_hash: str) -> SessionPin | None:
        """Any live pin under ``key`` whose prefix differs from ``prefix_hash``."""
        bucket = self._load_redis_bucket(key)
        if bucket is None:
            bucket = self._memory_bucket(key)
        else:
            bucket = {prefix: pin for prefix, pin in bucket.items() if self._pin_live(pin)}
        for prefix, pin in bucket.items():
            if prefix != prefix_hash:
                return pin
        return None

    def put(
        self,
        key: str,
        *,
        tier: str,
        model: str | None,
        prefix_hash: str,
    ) -> None:
        now = self._clock()
        expires = now + self.ttl_seconds if self.ttl_seconds > 0 else float("inf")
        pin = SessionPin(
            tier=tier,
            model=model,
            prefix_hash=prefix_hash,
            expires_at=expires,
        )
        bucket = self._load_redis_bucket(key)
        if bucket is None:
            bucket = dict(self._memory_bucket(key))
        else:
            bucket = {
                prefix: existing
                for prefix, existing in bucket.items()
                if self._pin_live(existing)
            }
        bucket[prefix_hash] = pin
        if self._save_redis_bucket(key, bucket):
            return
        self._pins[key] = bucket


def is_tool_result(message: Message) -> bool:
    if message.role == "tool":
        return True
    return bool(message.tool_call_id)


def is_tool_continuation(messages: list[Message]) -> bool:
    """Latest messages are tool results following an assistant tool-call."""
    if not messages:
        return False
    index = len(messages) - 1
    saw_tool = False
    while index >= 0 and is_tool_result(messages[index]):
        saw_tool = True
        index -= 1
    if not saw_tool:
        return False
    while index >= 0 and messages[index].role == "assistant":
        if messages[index].tool_calls:
            return True
        index -= 1
    return False


def conversation_prefix_hash(messages: list[Message]) -> str:
    """Stable hash of user/system turns, ignoring tool-result suffixes."""
    rows: list[dict[str, Any]] = []
    for message in messages:
        if is_tool_result(message):
            continue
        if message.role == "assistant" and message.tool_calls:
            continue
        if message.role not in {"system", "user"}:
            continue
        rows.append({"role": message.role, "content": message.content or ""})
    payload = json.dumps(rows, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode()).hexdigest()


def session_key(meta: object, prefix_hash: str) -> str:
    """Client session or user when present, otherwise the conversation prefix."""
    session = str(getattr(meta, "session_id", None) or "").strip()
    if session:
        return f"session:{session}"
    user = str(getattr(meta, "user", None) or "").strip()
    if user:
        return f"user:{user}"
    return f"prefix:{prefix_hash}"


def is_continuation(messages: list[Message], pin: SessionPin | None) -> bool:
    """Same conversation prefix as the stored pin (tool results or re-asks).

    Tool-result turns must still match ``pin.prefix_hash`` so a shared
    session/user key cannot replay another conversation's tier (#2267).
    """
    if pin is None:
        return False
    return conversation_prefix_hash(messages) == pin.prefix_hash


@dataclass(frozen=True)
class ProfilePin:
    """Category/complexity remembered for a user ask (#389)."""

    category: str
    complexity: str
    prefix_hash: str
    expires_at: float


class ProfilePinStore:
    """Memory of the last user-turn profile per session key (#389, #495)."""

    def __init__(
        self,
        ttl_seconds: float = 1800.0,
        *,
        clock: Callable[[], float] | None = None,
        redis_client: Any | None = None,
        redis_prefix: str = "daari:profile-pin:",
        redis_url: str | None = None,
        redis_timeout_seconds: float = 2.0,
    ) -> None:
        self.ttl_seconds = max(0.0, float(ttl_seconds))
        self._clock = clock or time.monotonic
        self._pins: dict[str, ProfilePin] = {}
        self._redis = redis_client
        self._redis_url = redis_url
        self._redis_timeout_seconds = redis_timeout_seconds
        self._redis_prefix = redis_prefix
        self._degraded = False

    def _client(self) -> Any | None:
        if self._redis is not None:
            return self._redis
        if not self._redis_url:
            return None
        from daari.cache.redis_client import connect_redis

        self._redis = connect_redis(
            self._redis_url, timeout_seconds=self._redis_timeout_seconds
        )
        return self._redis

    def _redis_key(self, key: str) -> str:
        return f"{self._redis_prefix}{key}"

    def _mark_degraded(self, exc: BaseException) -> None:
        if self._degraded:
            return
        self._degraded = True
        try:
            from daari.gateway.request_log import log_gateway_event

            log_gateway_event(
                "session_affinity.degraded",
                detail=str(exc),
                backend="redis",
                store="profile_pin",
            )
        except Exception:
            pass

    def get(self, key: str) -> ProfilePin | None:
        client = None
        try:
            client = self._client()
        except Exception as exc:
            self._mark_degraded(exc)
            client = None
        if client is not None:
            try:
                raw = client.get(self._redis_key(key))
                if raw is None:
                    return None
                if isinstance(raw, bytes):
                    raw = raw.decode()
                data = json.loads(raw)
                return ProfilePin(
                    category=str(data["category"]),
                    complexity=str(data["complexity"]),
                    prefix_hash=str(data.get("prefix_hash") or ""),
                    expires_at=float(data.get("expires_at") or 0.0),
                )
            except Exception as exc:
                self._mark_degraded(exc)
        pin = self._pins.get(key)
        if pin is None:
            return None
        if self.ttl_seconds > 0 and self._clock() >= pin.expires_at:
            self._pins.pop(key, None)
            return None
        return pin

    def put(
        self,
        key: str,
        *,
        category: str,
        complexity: str,
        prefix_hash: str,
    ) -> None:
        now = self._clock()
        expires = now + self.ttl_seconds if self.ttl_seconds > 0 else float("inf")
        pin = ProfilePin(
            category=category,
            complexity=complexity,
            prefix_hash=prefix_hash,
            expires_at=expires,
        )
        client = None
        try:
            client = self._client()
        except Exception as exc:
            self._mark_degraded(exc)
            client = None
        if client is not None:
            try:
                payload = json.dumps(
                    {
                        "category": pin.category,
                        "complexity": pin.complexity,
                        "prefix_hash": pin.prefix_hash,
                        "expires_at": pin.expires_at,
                    }
                )
                redis_key = self._redis_key(key)
                if self.ttl_seconds > 0:
                    client.set(redis_key, payload, ex=int(max(1, self.ttl_seconds)))
                else:
                    client.set(redis_key, payload)
                return
            except Exception as exc:
                self._mark_degraded(exc)
        self._pins[key] = pin


def user_turn_prefix(messages: list[Message]) -> list[Message]:
    """Drop a trailing tool-result suffix (and its assistant tool-calls)."""
    if not is_tool_continuation(messages):
        return list(messages)
    index = len(messages) - 1
    while index >= 0 and is_tool_result(messages[index]):
        index -= 1
    while index >= 0 and messages[index].role == "assistant" and messages[index].tool_calls:
        index -= 1
    return list(messages[: index + 1])
