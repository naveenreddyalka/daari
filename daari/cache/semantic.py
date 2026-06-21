from __future__ import annotations

import math
import time
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
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout

    async def embed(self, text: str) -> list[float] | None:
        if not text.strip():
            return None
        try:
            async with httpx.AsyncClient(base_url=self.base_url, timeout=self.timeout) as client:
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
    ) -> None:
        self.enabled = enabled
        self.embedder = embedder
        self.similarity_threshold = similarity_threshold
        self.max_entries = max_entries
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

    async def get(self, request: InternalRequest) -> tuple[InternalResponse | None, float | None]:
        if not self.enabled:
            return None, None

        text = extract_embed_text(request)
        if not text.strip():
            return None, None

        embedding = await self.embedder.embed(text)
        if embedding is None:
            return None, None

        context_key = semantic_context_key(request)
        best_score = 0.0
        best_entry: dict[str, Any] | None = None

        for entry in self._load_entries():
            if entry.get("context_key") != context_key:
                continue
            stored = entry.get("embedding")
            if not isinstance(stored, list):
                continue
            score = cosine_similarity(embedding, stored)
            if score > best_score:
                best_score = score
                best_entry = entry

        if best_entry is None or best_score < self.similarity_threshold:
            return None, best_score if best_score > 0 else None

        response = InternalResponse.model_validate_json(best_entry["response_json"])
        return response, best_score

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
                "created_at": time.time(),
            }
        )
        if len(entries) > self.max_entries:
            entries = entries[-self.max_entries :]
        self._save_entries(entries)
