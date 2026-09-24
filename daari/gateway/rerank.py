"""POST /v1/rerank — Cohere/LiteLLM-shaped L6 passthrough (#1051)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx
from fastapi import Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from daari.gateway.client_errors import summarize_upstream_failure
from daari.gateway.request_log import log_gateway_event

_UNAVAILABLE = (
    "Rerank requires a configured frontier (L6) OpenAI/Cohere-compatible "
    "endpoint. Set frontier.enabled=true and provide an API key; daari does "
    "not invent relevance scores locally."
)

_http: httpx.AsyncClient | None = None


def _shared_client() -> httpx.AsyncClient:
    global _http
    if _http is None or getattr(_http, "is_closed", False):
        from daari.router.http_pool import build_async_client

        _http = build_async_client(httpx)
    return _http


async def aclose_http() -> None:
    global _http
    if _http is not None and not getattr(_http, "is_closed", True):
        await _http.aclose()
    _http = None


@dataclass(frozen=True)
class RerankTarget:
    base_url: str
    api_key: str
    default_model: str
    timeout: float


class RerankRequest(BaseModel):
    query: str
    documents: list[str | dict[str, Any]]
    model: str | None = Field(default=None)
    top_n: int | None = Field(default=None, ge=1)


def _error(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"error": {"type": code, "message": message}},
    )


def normalize_documents(documents: list[str | dict[str, Any]]) -> list[str]:
    """Accept string docs or Cohere `{text: ...}` objects."""
    out: list[str] = []
    for doc in documents:
        if isinstance(doc, str):
            out.append(doc)
            continue
        if isinstance(doc, dict):
            text = doc.get("text")
            if isinstance(text, str):
                out.append(text)
                continue
        raise ValueError("each document must be a string or {text: string}")
    return out


def resolve_rerank_target(settings: Any) -> RerankTarget | None:
    frontier = getattr(settings, "frontier", None)
    if frontier is None or not bool(getattr(frontier, "enabled", False)):
        return None
    from daari.router.frontier_pool import build_frontier_pool
    from daari.security.secret_refs import SecretRefError

    pool = build_frontier_pool(settings)
    if not pool.slots:
        return None
    slot = pool.slots[0]
    try:
        key = slot.pick_key()
    except SecretRefError:
        return None
    secret = str(key or "").strip()
    if not secret:
        return None
    slot_base = str(getattr(slot.executor, "base_url", "") or "").strip().rstrip("/")
    if not slot_base:
        return None
    timeout = float(getattr(slot.executor, "timeout", 90.0) or 90.0)
    model = str(getattr(slot.executor, "default_model", "") or "").strip()
    if not model:
        model = str(getattr(frontier, "model", "") or "").strip() or "rerank-english-v3.0"
    return RerankTarget(
        base_url=slot_base,
        api_key=secret,
        default_model=model,
        timeout=timeout,
    )


async def post_rerank(
    url: str,
    *,
    headers: dict[str, str],
    payload: dict[str, Any],
    timeout: float,
) -> httpx.Response:
    return await _shared_client().post(url, headers=headers, json=payload, timeout=timeout)


async def handle_rerank(request: Request, body: RerankRequest) -> Any:
    ctx = request.app.state.ctx
    settings = ctx.settings
    target = resolve_rerank_target(settings)
    if target is None:
        log_gateway_event("rerank_unavailable", {"reason": "frontier_disabled_or_no_key"})
        return _error(501, "not_implemented", _UNAVAILABLE)

    try:
        documents = normalize_documents(body.documents)
    except ValueError as exc:
        return _error(400, "invalid_request", str(exc))
    if not documents:
        return _error(400, "invalid_request", "documents must be a non-empty list")

    model = (body.model or "").strip() or target.default_model
    payload: dict[str, Any] = {
        "model": model,
        "query": body.query,
        "documents": documents,
    }
    if body.top_n is not None:
        payload["top_n"] = body.top_n

    headers = {
        "Authorization": f"Bearer {target.api_key}",
        "Content-Type": "application/json",
    }
    url = f"{target.base_url}/rerank"
    try:
        upstream = await post_rerank(
            url, headers=headers, payload=payload, timeout=target.timeout
        )
    except Exception as exc:
        log_gateway_event(
            "rerank_upstream_error",
            {"error": summarize_upstream_failure(exc)},
        )
        return _error(503, "upstream_error", "Rerank upstream request failed.")

    if upstream.status_code >= 400:
        log_gateway_event("rerank_upstream_http", {"status": upstream.status_code})
        try:
            detail = upstream.json()
        except Exception:
            detail = {"error": {"type": "upstream_error", "message": upstream.text[:200]}}
        return JSONResponse(status_code=upstream.status_code, content=detail)

    try:
        data = upstream.json()
    except Exception:
        return _error(502, "bad_gateway", "Rerank upstream returned non-JSON.")
    log_gateway_event("rerank_ok", {"model": model, "docs": len(documents)})
    return data
