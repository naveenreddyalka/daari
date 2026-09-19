"""Shared embedding computation for OpenAI and Ollama facade routes."""

from __future__ import annotations

import json
import time
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


def _caller_client_id(request: Any | None) -> str | None:
    if request is None:
        return None
    claims = getattr(request.state, "auth_claims", None)
    if claims is None or getattr(claims, "kind", None) != "virtual":
        return None
    client_id = getattr(claims, "client_id", None) or getattr(claims, "key_id", None)
    text = str(client_id or "").strip()
    return text or None


def _bind_spend_context(
    request: Any,
    ctx: AppContext,
    *,
    model: str,
    client_id: str | None,
) -> None:
    """Copy virtual-key identity onto the chargeback row before the usage hook fires."""
    router = ctx.router
    ledger = getattr(router, "spend_ledger", None)
    if ledger is None or not getattr(ledger, "enabled", False):
        return
    from daari.observability.spend import SpendContext, bind_spend_context

    claims = getattr(request.state, "auth_claims", None)
    key_id = ""
    team_id = ""
    if claims is not None and getattr(claims, "kind", None) == "virtual":
        key_id = str(getattr(claims, "key_id", None) or "")
        virtual_key = getattr(claims, "virtual_key", None)
        if virtual_key is not None:
            team_id = str(getattr(virtual_key, "team_id", None) or "")
    usage = getattr(ctx.settings, "usage", None)
    fallback = float(getattr(usage, "frontier_price_per_1k_tokens", 0.002) or 0.002)
    pricing = getattr(router, "pricing", None) or getattr(ctx.settings, "pricing", None)
    bind_spend_context(
        SpendContext(
            key_id=key_id,
            team_id=team_id,
            client_id=client_id or "",
            requested_model=model,
            pricing=pricing,
            fallback_per_1k=fallback,
        )
    )


def _elapsed_ms(started: float) -> int:
    """Wall time in ms. Sub-millisecond work still counts as 1 so a miss is never 0."""
    elapsed = time.perf_counter() - started
    millis = int(elapsed * 1000)
    if millis <= 0 and elapsed > 0:
        return 1
    return max(0, millis)


async def compute_embeddings(
    ctx: AppContext,
    texts: list[str],
    *,
    model: str,
    request: Any | None = None,
) -> list[list[float]]:
    """Embed texts via L0 + semantic embedder; records metrics and ledger."""
    embedder = ctx.router.semantic_cache.embedder
    vectors: list[list[float]] = []
    cache_hits = 0
    latency_ms = 0
    for text in texts:
        cached = ctx.router.cache.get(embedding_cache_request(model, text))
        if cached is not None:
            vectors.append(json.loads(cached.content))
            cache_hits += 1
            continue
        started = time.perf_counter()
        embedding = await embedder.embed(text, model=model)
        latency_ms += _elapsed_ms(started)
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
        latency_ms=latency_ms,
    )
    client_id = _caller_client_id(request)
    if request is not None:
        _bind_spend_context(request, ctx, model=model, client_id=client_id)
    if ctx.router.usage_ledger is not None:
        ctx.router.usage_ledger.record(
            tier="embed",
            cache_hit=bool(texts) and cache_hits == len(texts),
            prompt_chars=prompt_chars,
            client_id=client_id,
            model=model,
            provider="ollama",
            input_tokens=estimate_tokens(prompt_chars),
            output_tokens=0,
        )
    return vectors


def openai_embeddings_payload(
    model: str, vectors: list[list[float]], texts: list[str]
) -> dict[str, Any]:
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
