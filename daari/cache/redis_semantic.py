"""Redis-backed L1 semantic cache for shared gateway replicas (issue #135).

Stores the same entry list shape as SemanticCache under a single Redis key so
replicas share nearest-neighbor hits. redis is optional (daari[redis]).
"""

from __future__ import annotations

import json
from typing import Any, Callable

from daari.cache.semantic import Embedder, SemanticCache


class RedisSemanticCache(SemanticCache):
    def __init__(
        self,
        redis_url: str,
        embedder: Embedder,
        *,
        prefix: str = "daari:l1:",
        enabled: bool = True,
        similarity_threshold: float = 0.88,
        max_entries: int = 1000,
        ttl_seconds: float = 0.0,
        clock: Callable[[], float] | None = None,
        normalize_inputs: bool = True,
        client: Any | None = None,
        verifier: Any = None,
        metrics: Any = None,
    ) -> None:
        super().__init__(
            path="redis",
            embedder=embedder,
            enabled=enabled,
            similarity_threshold=similarity_threshold,
            max_entries=max_entries,
            ttl_seconds=ttl_seconds,
            clock=clock,
            normalize_inputs=normalize_inputs,
            verifier=verifier,
            metrics=metrics,
        )
        self.redis_url = redis_url
        self.prefix = prefix
        self._client = client

    def _entries_redis_key(self) -> str:
        return f"{self.prefix}entries"

    def _redis(self) -> Any:
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

    def _store(self) -> Any:
        # Unused for Redis path; kept so base class callers don't break.
        return self._redis()

    def _load_entries(self) -> list[dict[str, Any]]:
        raw = self._redis().get(self._entries_redis_key())
        if raw is None:
            return []
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return []
        return data if isinstance(data, list) else []

    def _save_entries(self, entries: list[dict[str, Any]]) -> None:
        payload = json.dumps(entries)
        client = self._redis()
        key = self._entries_redis_key()
        if self.ttl_seconds > 0:
            # Refresh the whole list TTL on write; per-entry expiry still
            # enforced in _entry_expired during reads.
            client.set(key, payload, ex=int(self.ttl_seconds))
        else:
            client.set(key, payload)
