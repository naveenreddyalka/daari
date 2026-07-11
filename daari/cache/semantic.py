from __future__ import annotations

import hashlib
import math
import time
from collections import OrderedDict
from typing import Any, Protocol

import httpx

from daari.cache.exact import tools_schema_hash
from daari.gateway.internal import InternalRequest, InternalResponse


def extract_embed_text(request: InternalRequest) -> str:
    parts: list[str] = []
    for message in request.messages:
        if message.content:
            parts.append(f"{message.role}:{message.content}")
    return "\n".join(parts)


def semantic_context_key(request: InternalRequest) -> str:
    return "|".join(
        [
            request.model,
            str(request.temperature),
            tools_schema_hash(request.tools),
            request.meta.tier_override or "",
        ]
    )


def cosine_similarity(a: list[float], b: list[float]) -> float:
    if len(a) != len(b) or not a:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


class Embedder(Protocol):
    async def embed(self, text: str) -> list[float] | None: ...


class OllamaEmbedder:
    def __init__(
        self,
        base_url: str,
        model: str,
        *,
        timeout: float = 30.0,
        cache_size: int = 512,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self.cache_size = max(0, cache_size)
        self._transport = transport
        # LRU keyed by (model, text hash); embeddings for identical text are
        # deterministic, so memoizing skips an HTTP round-trip per L1 lookup.
        self._memo: OrderedDict[tuple[str, str], list[float]] = OrderedDict()

    def _cache_key(self, text: str) -> tuple[str, str]:
        return (self.model, hashlib.sha256(text.encode("utf-8")).hexdigest())

    async def embed(self, text: str) -> list[float] | None:
        if not text.strip():
            return None
        key = self._cache_key(text)
        if self.cache_size > 0 and key in self._memo:
            self._memo.move_to_end(key)
            return list(self._memo[key])
        embedding = await self._embed_http(text)
        if embedding is not None and self.cache_size > 0:
            self._memo[key] = list(embedding)
            while len(self._memo) > self.cache_size:
                self._memo.popitem(last=False)
        return embedding

    async def _embed_http(self, text: str) -> list[float] | None:
        try:
            async with httpx.AsyncClient(
                base_url=self.base_url, timeout=self.timeout, transport=self._transport
            ) as client:
                response = await client.post(
                    "/api/embeddings",
                    json={"model": self.model, "prompt": text},
                )
                response.raise_for_status()
                data = response.json()
                embedding = data.get("embedding")
                if isinstance(embedding, list) and embedding:
                    return [float(x) for x in embedding]
        except (httpx.HTTPError, ValueError, TypeError):
            return None
        return None


class SemanticCache:
    _entries_key = "_l1_entries"

    def __init__(
        self,
        path: str,
        embedder: Embedder,
        *,
        enabled: bool = True,
        similarity_threshold: float = 0.88,
        max_entries: int = 1000,
        ttl_seconds: float = 0.0,
        clock: Any = None,
    ) -> None:
        self.enabled = enabled
        self.embedder = embedder
        self.similarity_threshold = similarity_threshold
        self.max_entries = max_entries
        self.ttl_seconds = ttl_seconds
        self._clock = clock or time.time
        self._path = path
        self._cache: Any = None

    def _store(self) -> Any:
        if self._cache is None:
            import diskcache

            self._cache = diskcache.Cache(self._path)
        return self._cache

    def _load_entries(self) -> list[dict[str, Any]]:
        raw = self._store().get(self._entries_key, default=[])
        return raw if isinstance(raw, list) else []

    def _save_entries(self, entries: list[dict[str, Any]]) -> None:
        self._store().set(self._entries_key, entries)

    def _entry_expired(self, entry: dict[str, Any], max_age: float | None = None) -> bool:
        ttl = max_age if max_age is not None else self.ttl_seconds
        if ttl <= 0:
            return False
        created_at = entry.get("created_at")
        if not isinstance(created_at, (int, float)):
            return False
        return (self._clock() - created_at) > ttl

    async def nearest(
        self, request: InternalRequest, *, max_age: float | None = None
    ) -> tuple[InternalResponse | None, float]:
        """Best entry regardless of threshold — shared by the hit path and draft injection."""
        if not self.enabled:
            return None, 0.0

        text = extract_embed_text(request)
        if not text.strip():
            return None, 0.0

        embedding = await self.embedder.embed(text)
        if embedding is None:
            return None, 0.0

        context_key = semantic_context_key(request)
        best_score = 0.0
        best_entry: dict[str, Any] | None = None

        for entry in self._load_entries():
            if entry.get("context_key") != context_key:
                continue
            if self._entry_expired(entry, max_age):
                continue
            stored = entry.get("embedding")
            if not isinstance(stored, list):
                continue
            score = cosine_similarity(embedding, stored)
            if score > best_score:
                best_score = score
                best_entry = entry

        if best_entry is None:
            return None, 0.0
        return InternalResponse.model_validate_json(best_entry["response_json"]), best_score

    async def get(
        self, request: InternalRequest, *, max_age: float | None = None
    ) -> tuple[InternalResponse | None, float | None]:
        response, best_score = await self.nearest(request, max_age=max_age)
        if response is None or best_score < self.similarity_threshold:
            return None, best_score if best_score > 0 else None
        return response, best_score

    def prune(self) -> int:
        """Remove expired entries; returns how many were removed."""
        if self.ttl_seconds <= 0:
            return 0
        entries = self._load_entries()
        kept = [entry for entry in entries if not self._entry_expired(entry)]
        removed = len(entries) - len(kept)
        if removed:
            self._save_entries(kept)
        return removed

    async def put(self, request: InternalRequest, response: InternalResponse) -> None:
        if not self.enabled:
            return

        text = extract_embed_text(request)
        if not text.strip():
            return

        embedding = await self.embedder.embed(text)
        if embedding is None:
            return

        entries = self._load_entries()
        entries.append(
            {
                "context_key": semantic_context_key(request),
                "embedding": embedding,
                "response_json": response.model_dump_json(),
                "created_at": self._clock(),
            }
        )
        if len(entries) > self.max_entries:
            entries = entries[-self.max_entries :]
        self._save_entries(entries)
