from __future__ import annotations

import hashlib
import json
from typing import Any

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
    def __init__(self, path: str, enabled: bool = True) -> None:
        self.enabled = enabled
        self._path = path
        self._cache: Any = None

    def _store(self) -> Any:
        if self._cache is None:
            import diskcache

            self._cache = diskcache.Cache(self._path)
        return self._cache

    def get(self, request: InternalRequest) -> InternalResponse | None:
        if not self.enabled:
            return None
        raw = self._store().get(cache_key(request))
        if raw is None:
            return None
        return InternalResponse.model_validate_json(raw)

    def put(self, request: InternalRequest, response: InternalResponse) -> None:
        if not self.enabled:
            return
        self._store().set(cache_key(request), response.model_dump_json())
