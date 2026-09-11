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
    def __init__(
        self,
        ttl_seconds: float = 1800.0,
        *,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self.ttl_seconds = max(0.0, float(ttl_seconds))
        self._clock = clock or time.monotonic
        self._pins: dict[str, SessionPin] = {}

    def get(self, key: str) -> SessionPin | None:
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
        tier: str,
        model: str | None,
        prefix_hash: str,
    ) -> None:
        now = self._clock()
        expires = now + self.ttl_seconds if self.ttl_seconds > 0 else float("inf")
        self._pins[key] = SessionPin(
            tier=tier,
            model=model,
            prefix_hash=prefix_hash,
            expires_at=expires,
        )


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
    """Tool-result turn, or the same user-turn prefix as the stored pin."""
    if is_tool_continuation(messages):
        return True
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
    """In-process memory of the last user-turn profile per session key."""

    def __init__(
        self,
        ttl_seconds: float = 1800.0,
        *,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self.ttl_seconds = max(0.0, float(ttl_seconds))
        self._clock = clock or time.monotonic
        self._pins: dict[str, ProfilePin] = {}

    def get(self, key: str) -> ProfilePin | None:
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
        self._pins[key] = ProfilePin(
            category=category,
            complexity=complexity,
            prefix_hash=prefix_hash,
            expires_at=expires,
        )


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
