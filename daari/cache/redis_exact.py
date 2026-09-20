"""Redis-backed L0 exact cache for stateless gateway replicas (issue #112).

Duck-types ExactCache (get/put/prune). redis is an optional dependency —
missing install raises a clear error at first use, not at import time.
"""

from __future__ import annotations

from typing import Any, Callable

from daari.cache.exact import ExactCache, cache_key, cache_scope_segment
from daari.gateway.internal import InternalRequest, InternalResponse

# When L0 Redis TTL is off (ttl_seconds == 0), prune still reclaims entries
# older than this wall-clock age so unbounded fleets can shrink (#806).
REDIS_UNBOUNDED_PRUNE_MAX_AGE_SECONDS = 7 * 24 * 3600.0


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
        timeout_seconds: float = 2.0,
    ) -> None:
        # path unused — kept so callers can treat this like ExactCache.
        super().__init__(path="redis", enabled=enabled, ttl_seconds=ttl_seconds, clock=clock)
        self.redis_url = redis_url
        self.prefix = prefix
        self.timeout_seconds = timeout_seconds
        self._client = client

    def _store(self) -> Any:
        if self._client is None:
            from daari.cache.redis_client import connect_redis

            self._client = connect_redis(self.redis_url, timeout_seconds=self.timeout_seconds)
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

        entry: dict[str, Any] = {"v": response.model_dump_json(), "t": self._clock()}
        segment = cache_scope_segment(request)
        if segment:
            entry["scope"] = segment
        key = self._key(request)
        payload = json.dumps(entry)
        client = self._store()
        if self.ttl_seconds > 0:
            client.set(key, payload, ex=int(self.ttl_seconds))
        else:
            client.set(key, payload)

    def prune(self) -> int:
        """Drop aged L0 rows when Redis TTL is off; TTL fleets stay no-scan (#806)."""
        if not self.enabled:
            return 0
        if self.ttl_seconds > 0:
            # Keys were written with Redis EX; native TTL is the reclaim path.
            return 0
        client = self._store()
        removed = 0
        for key in self._prefixed_keys(client):
            entry = self._redis_entry_dict(client.get(key))
            if self._entry_expired(entry, REDIS_UNBOUNDED_PRUNE_MAX_AGE_SECONDS):
                deleted = client.delete(key)
                if deleted is None or deleted:
                    removed += 1
        return removed

    def invalidate(
        self,
        *,
        model: str | None = None,
        entry_hash: str | None = None,
        team_id: str | None = None,
        key_id: str | None = None,
    ) -> int:
        if not self.enabled:
            return 0
        client = self._store()
        removed = 0
        for key in self._prefixed_keys(client):
            bare = key[len(self.prefix) :] if key.startswith(self.prefix) else key
            if entry_hash is not None and bare != entry_hash and key != entry_hash:
                continue
            raw = client.get(key)
            if model is not None and self._redis_entry_model(raw) != model:
                continue
            entry = self._redis_entry_dict(raw)
            if not self._entry_matches_scope(entry, team_id=team_id, key_id=key_id):
                continue
            deleted = client.delete(key)
            if deleted is None or deleted:
                removed += 1
        return removed

    def _prefixed_keys(self, client: Any) -> list[str]:
        scan = getattr(client, "scan_iter", None)
        if scan is not None:
            return [str(key) for key in scan(match=f"{self.prefix}*")]
        keys = getattr(client, "keys", None)
        if keys is not None:
            found = keys(f"{self.prefix}*")
            return [str(key) for key in (found or [])]
        data = getattr(client, "data", None)
        if isinstance(data, dict):
            return [str(key) for key in data if str(key).startswith(self.prefix)]
        return []

    def _redis_entry_dict(self, raw: Any) -> Any:
        if raw is None:
            return None
        import json

        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return None

    def _redis_entry_model(self, raw: Any) -> str | None:
        return self._entry_model(self._redis_entry_dict(raw))
