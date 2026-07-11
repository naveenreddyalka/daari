from __future__ import annotations

import hashlib
import json
import time
from typing import Any, Callable

from daari.gateway.internal import InternalRequest, InternalResponse


def normalize_messages(messages: list[dict[str, Any]]) -> str:
    normalized: list[dict[str, Any]] = []
    for message in messages:
        entry: dict[str, Any] = {"role": message.get("role", "")}
        if message.get("content") is not None:
            entry["content"] = message["content"]
        if message.get("tool_calls"):
            entry["tool_calls"] = message["tool_calls"]
        normalized.append(entry)
    return json.dumps(normalized, sort_keys=True, separators=(",", ":"))


def tools_schema_hash(tools: list[Any] | None) -> str:
    if not tools:
        return ""
    return hashlib.sha256(
        json.dumps(tools, sort_keys=True, default=str).encode()
    ).hexdigest()


def cache_key(request: InternalRequest) -> str:
    payload = "|".join(
        [
            normalize_messages([m.model_dump() for m in request.messages]),
            request.model,
            str(request.temperature),
            tools_schema_hash(request.tools),
            request.meta.tier_override or "",
        ]
    )
    return hashlib.sha256(payload.encode()).hexdigest()


class ExactCache:
    def __init__(
        self,
        path: str,
        enabled: bool = True,
        *,
        ttl_seconds: float = 0.0,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self.enabled = enabled
        self.ttl_seconds = ttl_seconds
        self._clock = clock or time.time
        self._path = path
        self._cache: Any = None

    def _store(self) -> Any:
        if self._cache is None:
            import diskcache

            self._cache = diskcache.Cache(self._path)
        return self._cache

    def _entry_expired(self, entry: Any, max_age: float | None) -> bool:
        ttl = max_age if max_age is not None else self.ttl_seconds
        if ttl <= 0:
            return False
        # Legacy entries (raw json string) carry no timestamp; treat as fresh.
        if not isinstance(entry, dict):
            return False
        stored_at = entry.get("t")
        if not isinstance(stored_at, (int, float)):
            return False
        return (self._clock() - stored_at) > ttl

    @staticmethod
    def _entry_value(entry: Any) -> str | None:
        if isinstance(entry, dict):
            value = entry.get("v")
            return value if isinstance(value, str) else None
        return entry if isinstance(entry, str) else None

    def get(self, request: InternalRequest, *, max_age: float | None = None) -> InternalResponse | None:
        if not self.enabled:
            return None
        key = cache_key(request)
        entry = self._store().get(key)
        if entry is None:
            return None
        if self._entry_expired(entry, max_age):
            self._store().delete(key)
            return None
        raw = self._entry_value(entry)
        if raw is None:
            return None
        return InternalResponse.model_validate_json(raw)

    def put(self, request: InternalRequest, response: InternalResponse) -> None:
        if not self.enabled:
            return
        self._store().set(
            cache_key(request),
            {"v": response.model_dump_json(), "t": self._clock()},
        )

    def prune(self) -> int:
        """Remove expired entries; returns how many were removed."""
        if self.ttl_seconds <= 0:
            return 0
        store = self._store()
        removed = 0
        for key in list(store.iterkeys()):
            entry = store.get(key)
            if self._entry_expired(entry, None):
                store.delete(key)
                removed += 1
        return removed
