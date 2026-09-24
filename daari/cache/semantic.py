from __future__ import annotations

import hashlib
import json
import math
import time
from collections import OrderedDict
from typing import Any, Protocol

import httpx

from daari.cache.exact import cache_scope_segment, tools_schema_hash
from daari.cache.normalize import normalize_for_embedding
from daari.cache.singleflight import SingleFlight
from daari.gateway.internal import InternalRequest, InternalResponse
from daari.gateway.request_log import log_gateway_event


def extract_embed_text(request: InternalRequest) -> str:
    parts: list[str] = []
    for message in request.messages:
        chunk = message.content or ""
        if message.audio:
            tokens = ",".join(clip.cache_token() for clip in message.audio)
            suffix = f"audio:{tokens}"
            chunk = f"{chunk}|{suffix}" if chunk else suffix
        if chunk:
            parts.append(f"{message.role}:{chunk}")
    return "\n".join(parts)


def _split_agent_messages(request: InternalRequest) -> tuple[list[Any], list[Any]]:
    """Stable prefix vs the trailing tool results that change every agent turn."""
    messages = request.messages
    end = len(messages)
    while end > 0 and messages[end - 1].role == "tool":
        end -= 1
    return messages[:end], messages[end:]


def agent_prefix_text(request: InternalRequest) -> str:
    """Embeddable text for the stable prefix (system + history minus tool results)."""
    prefix, _ = _split_agent_messages(request)
    return "\n".join(
        f"{message.role}:{message.content}" for message in prefix if message.content
    )


def agent_suffix_hash(request: InternalRequest) -> str:
    """Exact hash of the trailing tool results — a changed result must not reuse an answer."""
    _, suffix = _split_agent_messages(request)
    payload = json.dumps(
        [[message.role, message.content or ""] for message in suffix], sort_keys=True
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def semantic_context_key(
    request: InternalRequest,
    *,
    embedding_model: str | None = None,
) -> str:
    """L1 namespace: model/temperature/tools/tier/scope + embedder identity (#845)."""
    parts = [
        request.model,
        str(request.temperature),
        tools_schema_hash(request.tools),
        request.meta.tier_override or "",
    ]
    segment = cache_scope_segment(request)
    if segment:
        parts.append(segment)
    embed = (embedding_model or "").strip()
    if embed:
        parts.append(f"embed:{embed}")
    return "|".join(parts)


def l1_flight_key(
    request: InternalRequest,
    *,
    text: str | None = None,
    context_key: str | None = None,
) -> str:
    """In-process singleflight key for identical normalized embeds (#517).

    Near-identical Ask prompts that collapse to the same embed text share one
    nearest/fill; exact L0 keys may still differ (whitespace, scaffolding).
    """
    ctx = context_key if context_key is not None else semantic_context_key(request)
    embed_text = text if text is not None else extract_embed_text(request)
    digest = hashlib.sha256(embed_text.encode("utf-8")).hexdigest()
    return f"{ctx}|{digest}"


def cosine_similarity(a: list[float], b: list[float]) -> float:
    if len(a) != len(b) or not a:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


def _semantic_entry_matches(
    entry: dict[str, Any],
    *,
    model: str | None,
    entry_hash: str | None,
    team_id: str | None = None,
    key_id: str | None = None,
) -> bool:
    """True when the row should be dropped. Unset filters match everything."""
    if model is None and entry_hash is None and team_id is None and key_id is None:
        return True
    ctx = str(entry.get("context_key") or "")
    segments = ctx.split("|")
    if model is not None:
        if ctx != model and not ctx.startswith(f"{model}|"):
            return False
    if entry_hash is not None and entry.get("answer_hash") != entry_hash:
        return False
    if team_id is not None and f"team:{team_id}" not in segments:
        return False
    if key_id is not None and f"key:{key_id}" not in segments:
        return False
    return True


class Embedder(Protocol):
    async def embed(self, text: str, *, model: str | None = None) -> list[float] | None: ...


class OllamaEmbedder:
    def __init__(
        self,
        base_url: str,
        model: str,
        *,
        timeout: float = 30.0,
        cache_size: int = 512,
        transport: httpx.AsyncBaseTransport | None = None,
        pool_limits: Any = None,
        retry: Any | None = None,
        metrics: Any | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self.cache_size = max(0, cache_size)
        self._transport = transport
        self.pool_limits = pool_limits
        self.retry = retry
        self.metrics = metrics
        self._http: httpx.AsyncClient | None = None
        # LRU keyed by (model, text hash); embeddings for identical text are
        # deterministic, so memoizing skips an HTTP round-trip per L1 lookup.
        self._memo: OrderedDict[tuple[str, str], list[float]] = OrderedDict()

    def _client(self) -> httpx.AsyncClient:
        if self._http is None or getattr(self._http, "is_closed", False):
            from daari.router.http_pool import PoolLimits, build_async_client

            self._http = build_async_client(
                httpx,
                base_url=self.base_url,
                limits=self.pool_limits or PoolLimits(),
                transport=self._transport,
            )
        return self._http

    async def aclose(self) -> None:
        if self._http is not None and not getattr(self._http, "is_closed", True):
            await self._http.aclose()
        self._http = None

    def _cache_key(self, text: str) -> tuple[str, str]:
        return (self.model, hashlib.sha256(text.encode("utf-8")).hexdigest())

    def _memo_key(self, text: str, model: str) -> tuple[str, str]:
        return (model, hashlib.sha256(text.encode("utf-8")).hexdigest())

    def _memo_get(self, key: tuple[str, str]) -> list[float] | None:
        if self.cache_size <= 0 or key not in self._memo:
            return None
        self._memo.move_to_end(key)
        return list(self._memo[key])

    def _memo_put(self, key: tuple[str, str], embedding: list[float]) -> None:
        if self.cache_size <= 0:
            return
        self._memo[key] = list(embedding)
        while len(self._memo) > self.cache_size:
            self._memo.popitem(last=False)

    async def embed(self, text: str, *, model: str | None = None) -> list[float] | None:
        results = await self.embed_many([text], model=model)
        return results[0] if results else None

    async def embed_many(
        self, texts: list[str], *, model: str | None = None
    ) -> list[list[float] | None]:
        used_model = model or self.model
        results: list[list[float] | None] = [None] * len(texts)
        miss_indices: list[int] = []
        miss_texts: list[str] = []
        for index, text in enumerate(texts):
            if not text.strip():
                continue
            cached = self._memo_get(self._memo_key(text, used_model))
            if cached is not None:
                results[index] = cached
                continue
            miss_indices.append(index)
            miss_texts.append(text)
        if not miss_texts:
            return results
        fetched = await self._embed_http_batch(miss_texts, model=used_model)
        if fetched is None:
            fetched = [
                await self._embed_http(text, model=used_model) for text in miss_texts
            ]
        for index, embedding in zip(miss_indices, fetched, strict=True):
            if embedding is not None:
                self._memo_put(self._memo_key(texts[index], used_model), embedding)
            results[index] = embedding
        return results

    async def _embed_http_batch(
        self, texts: list[str], *, model: str
    ) -> list[list[float] | None] | None:
        """POST /api/embed with input[]. None means the server needs the legacy path."""
        from daari.router.deadline import nonstream_timeout
        from daari.router.retry import RETRYABLE_STATUS, RetryPolicy, run_upstream

        try:
            timeout = nonstream_timeout(self.timeout, "embed")
            from daari.observability.otel import inject_trace_headers

            policy = (
                self.retry
                if isinstance(self.retry, RetryPolicy)
                else (
                    RetryPolicy(attempts=1)
                    if self.retry is None
                    else RetryPolicy.from_settings(self.retry)
                )
            )

            async def attempt() -> httpx.Response:
                response = await self._client().post(
                    "/api/embed",
                    json={"model": model, "input": texts},
                    headers=inject_trace_headers(),
                    timeout=timeout,
                )
                if response.status_code in RETRYABLE_STATUS:
                    response.raise_for_status()
                return response

            response = await run_upstream(
                attempt,
                upstream="embed",
                policy=policy,
                timeout=timeout,
                metrics=self.metrics,
            )
            if response.status_code == 404:
                return None
            response.raise_for_status()
            data = response.json()
            embeddings = data.get("embeddings")
            if not isinstance(embeddings, list) or len(embeddings) != len(texts):
                return [None] * len(texts)
            parsed: list[list[float] | None] = []
            for embedding in embeddings:
                if isinstance(embedding, list) and embedding:
                    parsed.append([float(x) for x in embedding])
                else:
                    parsed.append(None)
            return parsed
        except (httpx.HTTPError, ValueError, TypeError):
            return [None] * len(texts)

    async def _embed_http(self, text: str, *, model: str) -> list[float] | None:
        from daari.router.deadline import nonstream_timeout
        from daari.router.retry import RETRYABLE_STATUS, RetryPolicy, run_upstream

        try:
            timeout = nonstream_timeout(self.timeout, "embed")
            from daari.observability.otel import inject_trace_headers

            policy = (
                self.retry
                if isinstance(self.retry, RetryPolicy)
                else (
                    RetryPolicy(attempts=1)
                    if self.retry is None
                    else RetryPolicy.from_settings(self.retry)
                )
            )

            async def attempt() -> httpx.Response:
                response = await self._client().post(
                    "/api/embeddings",
                    json={"model": model, "prompt": text},
                    headers=inject_trace_headers(),
                    timeout=timeout,
                )
                if response.status_code in RETRYABLE_STATUS:
                    response.raise_for_status()
                return response

            response = await run_upstream(
                attempt,
                upstream="embed",
                policy=policy,
                timeout=timeout,
                metrics=self.metrics,
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
        normalize_inputs: bool = True,
        verifier: Any = None,
        metrics: Any = None,
    ) -> None:
        self.enabled = enabled
        self.embedder = embedder
        self.similarity_threshold = similarity_threshold
        self.max_entries = max_entries
        self.ttl_seconds = ttl_seconds
        self.normalize_inputs = normalize_inputs
        self.verifier = verifier
        self.metrics = metrics
        self._clock = clock or time.time
        self._path = path
        self._cache: Any = None
        # Concurrent same-key nearest() share one embed+scan (#517).
        self._lookup_flight = SingleFlight()

    def _embedding_model_id(self) -> str | None:
        raw = getattr(self.embedder, "model", None)
        text = str(raw or "").strip()
        return text or None

    def _context_key(self, request: InternalRequest) -> str:
        return semantic_context_key(request, embedding_model=self._embedding_model_id())

    def flight_key(
        self,
        request: InternalRequest,
        *,
        context_key: str | None = None,
        text: str | None = None,
    ) -> str:
        embed_text = text if text is not None else self._embed_text(request)
        return l1_flight_key(
            request,
            text=embed_text,
            context_key=context_key if context_key is not None else self._context_key(request),
        )

    def _embed_text(self, request: InternalRequest) -> str:
        text = extract_embed_text(request)
        if self.normalize_inputs:
            normalized = normalize_for_embedding(text)
            # Never normalize down to nothing — fall back to the raw text.
            return normalized or text
        return text

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
        response, score, _ = await self._nearest_entry(request, max_age=max_age)
        return response, score

    async def nearest_with_source(
        self, request: InternalRequest, *, max_age: float | None = None
    ) -> tuple[InternalResponse | None, float, str | None]:
        """`nearest()` plus the stored prompt text, so serve paths can verify (#206)."""
        return await self._nearest_entry(request, max_age=max_age)

    def verify_for_serving(self, request: InternalRequest, stored_text: str | None) -> bool:
        """Second-stage veto for serve paths that use nearest() instead of get() (#206).

        True when no verifier is configured or the candidate passes; False vetoes
        the hit (and logs/counts the avoided false hit via `_verified`).
        """
        if self.verifier is None:
            return True
        return self._verified(request, stored_text)

    def _agent_context_key(self, request: InternalRequest) -> str:
        # The suffix hash is part of the key, so a changed last tool result can
        # never cosine-match the answer produced from the previous one (G1b).
        return "|".join(
            ["agent-prefix", self._context_key(request), agent_suffix_hash(request)]
        )

    def _agent_prefix_text(self, request: InternalRequest) -> str:
        text = agent_prefix_text(request)
        if self.normalize_inputs:
            return normalize_for_embedding(text) or text
        return text

    async def nearest_agent_prefix(
        self, request: InternalRequest, *, max_age: float | None = None
    ) -> tuple[InternalResponse | None, float, str | None]:
        return await self._nearest_entry(
            request,
            max_age=max_age,
            context_key=self._agent_context_key(request),
            text=self._agent_prefix_text(request),
        )

    async def put_agent_prefix(
        self, request: InternalRequest, response: InternalResponse
    ) -> None:
        await self._put(
            request,
            response,
            context_key=self._agent_context_key(request),
            text=self._agent_prefix_text(request),
        )

    async def _nearest_entry(
        self,
        request: InternalRequest,
        *,
        max_age: float | None = None,
        context_key: str | None = None,
        text: str | None = None,
    ) -> tuple[InternalResponse | None, float, str | None]:
        """Best entry plus the prompt that produced it, for verification (#168).

        The stored text is returned rather than stashed on the instance because
        concurrent requests share this object. Concurrent identical embed keys
        share one embed+scan via singleflight (#517).
        """
        if not self.enabled:
            return None, 0.0, None

        text = text if text is not None else self._embed_text(request)
        if not text.strip():
            return None, 0.0, None

        ctx = context_key or self._context_key(request)
        flight = f"{self.flight_key(request, context_key=ctx, text=text)}|age={max_age}"

        async def _scan() -> tuple[InternalResponse | None, float, str | None]:
            return await self._nearest_entry_uncached(
                request, max_age=max_age, context_key=ctx, text=text
            )

        response, score, source = await self._lookup_flight.do(flight, _scan)
        if response is None:
            return None, score, source
        # Waiters mutate daari_meta on serve paths; isolate copies.
        return response.model_copy(deep=True), score, source

    async def _nearest_entry_uncached(
        self,
        request: InternalRequest,
        *,
        max_age: float | None = None,
        context_key: str | None = None,
        text: str | None = None,
    ) -> tuple[InternalResponse | None, float, str | None]:
        text = text if text is not None else self._embed_text(request)
        if not text.strip():
            return None, 0.0, None

        embedding = await self.embedder.embed(text)
        if embedding is None:
            return None, 0.0, None

        context_key = context_key or self._context_key(request)
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
            return None, 0.0, None
        return (
            InternalResponse.model_validate_json(best_entry["response_json"]),
            best_score,
            best_entry.get("prompt_text"),
        )

    async def get(
        self, request: InternalRequest, *, max_age: float | None = None
    ) -> tuple[InternalResponse | None, float | None]:
        response, best_score, stored_text = await self._nearest_entry(request, max_age=max_age)
        if response is None or best_score < self.similarity_threshold:
            return None, best_score if best_score > 0 else None
        if self.verifier is not None and not self._verified(request, stored_text):
            return None, best_score
        return response, best_score

    def _verified(self, request: InternalRequest, stored_text: str | None) -> bool:
        """Second stage between cosine and serve (#168).

        A candidate that cannot be checked is not served: entries written before
        verification existed carry no prompt text, so serving them would keep
        exactly the false hits this exists to stop. They are re-learned on the
        next miss.
        """
        if not stored_text:
            self._record_avoided("unverifiable_entry")
            return False
        result = self.verifier.verify(self._embed_text(request), stored_text)
        if result.ok:
            return True
        self._record_avoided(result.reason or "rejected")
        return False

    def _record_avoided(self, reason: str) -> None:
        if self.metrics is not None and hasattr(self.metrics, "record_false_hit_avoided"):
            self.metrics.record_false_hit_avoided()
        log_gateway_event("l1_verification_rejected", {"reason": reason})

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

    def invalidate(
        self,
        *,
        model: str | None = None,
        entry_hash: str | None = None,
        team_id: str | None = None,
        key_id: str | None = None,
    ) -> int:
        """Drop L1 rows by context_key model prefix, answer hash, tenant, or all."""
        if not self.enabled:
            return 0
        entries = self._load_entries()
        kept: list[dict[str, Any]] = []
        removed = 0
        for entry in entries:
            if _semantic_entry_matches(
                entry,
                model=model,
                entry_hash=entry_hash,
                team_id=team_id,
                key_id=key_id,
            ):
                removed += 1
            else:
                kept.append(entry)
        if removed:
            self._save_entries(kept)
        return removed

    async def put(self, request: InternalRequest, response: InternalResponse) -> None:
        await self._put(request, response)

    async def _put(
        self,
        request: InternalRequest,
        response: InternalResponse,
        *,
        context_key: str | None = None,
        text: str | None = None,
    ) -> None:
        if not self.enabled:
            return

        text = text if text is not None else self._embed_text(request)
        if not text.strip():
            return

        embedding = await self.embedder.embed(text)
        if embedding is None:
            return

        # Lazy import avoids a load-time cycle (router imports this module).
        try:
            from daari.router.profile import build_prompt_profile

            category = build_prompt_profile(request).category
        except Exception:
            category = "unknown"

        entries = self._load_entries()
        entries.append(
            {
                "context_key": context_key or self._context_key(request),
                "embedding": embedding,
                # Kept so a hit can be verified against the question that
                # produced it, not just its embedding (#168).
                "prompt_text": text,
                "response_json": response.model_dump_json(),
                "created_at": self._clock(),
                "category": category,
                "answer_hash": hashlib.sha256(
                    (response.content or "").encode("utf-8")
                ).hexdigest(),
            }
        )
        if len(entries) > self.max_entries:
            entries = self._trim_entries(entries)
        self._save_entries(entries)

    def _trim_entries(self, entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Keep newest max_entries; drop other-embedder rows first (#845)."""
        if len(entries) <= self.max_entries:
            return entries
        embed_id = self._embedding_model_id()
        marker = f"embed:{embed_id}" if embed_id else None
        if marker:
            current = [e for e in entries if marker in str(e.get("context_key") or "")]
            stale = [e for e in entries if marker not in str(e.get("context_key") or "")]
            # Prefer discarding stale-model rows before touching the live set.
            if len(current) >= self.max_entries:
                return current[-self.max_entries :]
            need = self.max_entries - len(current)
            return stale[-need:] + current if need > 0 else current
        return entries[-self.max_entries :]

    def diversity_stats(self) -> dict[str, dict[str, Any]]:
        """Unique-answer ratio per category (Trust PRD T1b).

        A category serving one unique answer across many distinct prompts is
        the canonical broken-cache signal.
        """
        grouped: dict[str, dict[str, Any]] = {}
        for entry in self._load_entries():
            category = entry.get("category") or "unknown"
            bucket = grouped.setdefault(category, {"entries": 0, "hashes": set()})
            bucket["entries"] += 1
            bucket["hashes"].add(entry.get("answer_hash") or entry.get("response_json"))
        return {
            category: {
                "entries": bucket["entries"],
                "unique_answers": len(bucket["hashes"]),
                "ratio": round(len(bucket["hashes"]) / bucket["entries"], 4),
            }
            for category, bucket in grouped.items()
        }
