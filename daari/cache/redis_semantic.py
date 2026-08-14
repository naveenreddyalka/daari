"""Redis-backed L1 semantic cache for shared gateway replicas (issue #135).

Stores the same entry list shape as SemanticCache under a single Redis key so
replicas share nearest-neighbor hits. redis is optional (daari[redis]).
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Callable

from daari.cache.semantic import Embedder, SemanticCache, semantic_context_key
from daari.gateway.internal import InternalRequest, InternalResponse


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

    def _parse_entries(self, raw: Any) -> list[dict[str, Any]]:
        if raw is None:
            return []
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return []
        return data if isinstance(data, list) else []

    def _load_entries(self) -> list[dict[str, Any]]:
        return self._parse_entries(self._redis().get(self._entries_redis_key()))

    def _write_entries(self, client: Any, key: str, entries: list[dict[str, Any]]) -> None:
        payload = json.dumps(entries)
        if self.ttl_seconds > 0:
            client.set(key, payload, ex=int(self.ttl_seconds))
        else:
            client.set(key, payload)

    def _save_entries(self, entries: list[dict[str, Any]]) -> None:
        self._write_entries(self._redis(), self._entries_redis_key(), entries)

    def _watch_conflict(self, exc: BaseException) -> bool:
        return type(exc).__name__ == "WatchError"

    def _mutate_entries(self, mutator: Callable[[list[dict[str, Any]]], list[dict[str, Any]]]) -> None:
        """Optimistic lock around the entry-list blob (issue #150).

        Contended writes retry a bounded number of times, then persist the
        latest snapshot without raising into the request path.
        """
        client = self._redis()
        key = self._entries_redis_key()
        pipeline_fn = getattr(client, "pipeline", None)
        if pipeline_fn is None:
            self._save_entries(mutator(self._load_entries()))
            return
        for _ in range(self._CAS_ATTEMPTS):
            pipe = pipeline_fn()
            try:
                if hasattr(pipe, "watch"):
                    pipe.watch(key)
                raw = pipe.get(key) if hasattr(pipe, "get") else client.get(key)
                updated = mutator(self._parse_entries(raw))
                if hasattr(pipe, "multi"):
                    pipe.multi()
                if self.ttl_seconds > 0:
                    pipe.set(key, json.dumps(updated), ex=int(self.ttl_seconds))
                else:
                    pipe.set(key, json.dumps(updated))
                pipe.execute()
                return
            except Exception as exc:  # noqa: BLE001 — WatchError is client-specific
                if not self._watch_conflict(exc):
                    raise
                if hasattr(pipe, "reset"):
                    pipe.reset()
                continue
        self._save_entries(mutator(self._load_entries()))

    _CAS_ATTEMPTS = 5

    async def put(self, request: InternalRequest, response: InternalResponse) -> None:
        if not self.enabled:
            return
        text = self._embed_text(request)
        if not text.strip():
            return
        embedding = await self.embedder.embed(text)
        if embedding is None:
            return
        try:
            from daari.router.profile import build_prompt_profile

            category = build_prompt_profile(request).category
        except Exception:
            category = "unknown"
        new_entry = {
            "context_key": semantic_context_key(request),
            "embedding": embedding,
            "prompt_text": text,
            "response_json": response.model_dump_json(),
            "created_at": self._clock(),
            "category": category,
            "answer_hash": hashlib.sha256(
                (response.content or "").encode("utf-8")
            ).hexdigest(),
        }

        def append(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
            entries = list(entries)
            entries.append(new_entry)
            if len(entries) > self.max_entries:
                return entries[-self.max_entries :]
            return entries

        self._mutate_entries(append)

    def prune(self) -> int:
        if self.ttl_seconds <= 0:
            return 0
        removed = 0

        def drop_expired(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
            nonlocal removed
            kept = [entry for entry in entries if not self._entry_expired(entry)]
            removed = len(entries) - len(kept)
            return kept

        self._mutate_entries(drop_expired)
        return removed
