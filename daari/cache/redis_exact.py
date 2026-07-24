"""Redis-backed L0 exact cache for stateless gateway replicas (issue #112).

Duck-types ExactCache (get/put/prune). redis is an optional dependency —
missing install raises a clear error at first use, not at import time.
"""

from __future__ import annotations

from typing import Any, Callable

from daari.cache.exact import ExactCache, cache_key
from daari.gateway.internal import InternalRequest, InternalResponse


class RedisExactCache(ExactCache):
    def __init__(
        self,
        redis_url: str,
        *,
        prefix: str = "daari:l0:",
        enabled: bool = True,
        ttl_seconds: float = 0.0,
        clock: Callable[[], float] | None = None,
        client: Any | None = None,
    ) -> None:
        # path unused — kept so callers can treat this like ExactCache.
        super().__init__(path="redis", enabled=enabled, ttl_seconds=ttl_seconds, clock=clock)
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

    def _key(self, request: InternalRequest) -> str:
        return f"{self.prefix}{cache_key(request)}"

    def get(self, request: InternalRequest, *, max_age: float | None = None) -> InternalResponse | None:
        if not self.enabled:
            return None
        raw = self._store().get(self._key(request))
        if raw is None:
            return None
        import json

        try:
            entry = json.loads(raw)
        except json.JSONDecodeError:
            return None
        if self._entry_expired(entry, max_age):
            self._store().delete(self._key(request))
            return None
        value = self._entry_value(entry)
        if value is None:
            return None
        return InternalResponse.model_validate_json(value)

    def put(self, request: InternalRequest, response: InternalResponse) -> None:
        if not self.enabled:
            return
        import json

        entry = {"v": response.model_dump_json(), "t": self._clock()}
        key = self._key(request)
        payload = json.dumps(entry)
        client = self._store()
        if self.ttl_seconds > 0:
            client.set(key, payload, ex=int(self.ttl_seconds))
        else:
            client.set(key, payload)

    def prune(self) -> int:
        # Redis TTLs handle expiry when ttl_seconds > 0; otherwise no-op.
        return 0
