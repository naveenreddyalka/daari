"""Shared embedding computation for OpenAI and Ollama facade routes."""

from __future__ import annotations

import json
from typing import Any

from fastapi import HTTPException

from daari.gateway.internal import DaariMeta, InternalRequest, InternalResponse, Message
from daari.observability.tokens import estimate_tokens
from daari.router.router import AppContext


def embedding_texts(value: str | list[str]) -> list[str]:
    if isinstance(value, str):
        return [value]
    return [str(item) for item in value]


def embedding_cache_request(model: str, text: str) -> InternalRequest:
    return InternalRequest(
        messages=[Message(role="user", content=text)],
        model=f"__embed__:{model}",
    )


def resolve_embedding_model(ctx: AppContext, requested: str) -> str:
    configured = ctx.settings.cache.l1.embedding_model
    name = (requested or "").strip() or "daari"
    if name not in {"daari", configured}:
        raise HTTPException(status_code=400, detail=f"unknown embedding model: {name}")
    return configured


async def compute_embeddings(
    ctx: AppContext,
    texts: list[str],
    *,
    model: str,
) -> list[list[float]]:
    """Embed texts via L0 + semantic embedder; records metrics and ledger."""
    embedder = ctx.router.semantic_cache.embedder
    vectors: list[list[float]] = []
    cache_hits = 0
    for text in texts:
        cached = ctx.router.cache.get(embedding_cache_request(model, text))
        if cached is not None:
            vectors.append(json.loads(cached.content))
            cache_hits += 1
            continue
        embedding = await embedder.embed(text, model=model)
        if embedding is None:
            raise HTTPException(
                status_code=502, detail=f"embedding model {model} returned no vector"
            )
        ctx.router.cache.put(
            embedding_cache_request(model, text),
            InternalResponse(
                content=json.dumps(embedding),
                model=model,
                daari_meta=DaariMeta(
                    tier="embed",
                    cache_hit=False,
                    executor="ollama",
                    provider_id="ollama",
                    model=model,
                ),
            ),
        )
        vectors.append(embedding)
    prompt_chars = sum(len(text) for text in texts)
    ctx.metrics.record(
        "embed",
        cache_hit=bool(texts) and cache_hits == len(texts),
        latency_ms=0,
    )
    if ctx.router.usage_ledger is not None:
        ctx.router.usage_ledger.record(
            tier="embed",
            cache_hit=bool(texts) and cache_hits == len(texts),
            prompt_chars=prompt_chars,
            model=model,
            provider="ollama",
            input_tokens=estimate_tokens(prompt_chars),
            output_tokens=0,
        )
    return vectors


def openai_embeddings_payload(model: str, vectors: list[list[float]], texts: list[str]) -> dict[str, Any]:
    prompt_chars = sum(len(text) for text in texts)
    return {
        "object": "list",
        "data": [
            {"object": "embedding", "index": index, "embedding": vector}
            for index, vector in enumerate(vectors)
        ],
        "model": model,
        "usage": {
            "prompt_tokens": estimate_tokens(prompt_chars),
            "total_tokens": estimate_tokens(prompt_chars),
        },
    }
