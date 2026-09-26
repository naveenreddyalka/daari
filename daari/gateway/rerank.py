"""POST /v1/rerank — Cohere/LiteLLM-shaped L6 passthrough (#1051, #1058, #1060)."""

from __future__ import annotations

from typing import Any

import httpx
from fastapi import Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from daari.gateway.client_errors import summarize_upstream_failure
from daari.gateway.l6_passthrough import (
    L6Target,
    RegionUnavailable,
    is_slot_failure,
    post_l6,
    region_pin_from_request,
    resolve_l6_targets,
)
from daari.gateway.request_log import log_gateway_event

_UNAVAILABLE = (
    "Rerank requires a configured frontier (L6) OpenAI/Cohere-compatible "
    "endpoint. Set frontier.enabled=true and provide an API key; daari does "
    "not invent relevance scores locally."
)

RerankTarget = L6Target

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


def resolve_rerank_target(
    settings: Any, *, region_pin: str | None = None
) -> RerankTarget | None:
    try:
        targets = resolve_l6_targets(
            settings, region_pin=region_pin, default_model="rerank-english-v3.0"
        )
    except RegionUnavailable:
        return None
    return targets[0] if targets else None


async def post_rerank(
    url: str,
    *,
    headers: dict[str, str],
    payload: dict[str, Any],
    timeout: float,
    retry: Any | None = None,
    metrics: Any | None = None,
) -> httpx.Response:
    return await post_l6(
        _shared_client(),
        url,
        headers=headers,
        payload=payload,
        timeout=timeout,
        upstream="rerank",
        retry=retry,
        metrics=metrics,
    )


def _caller_client_id(request: Request) -> str | None:
    claims = getattr(request.state, "auth_claims", None)
    if claims is None or getattr(claims, "kind", None) != "virtual":
        return None
    client_id = getattr(claims, "client_id", None) or getattr(claims, "key_id", None)
    text = str(client_id or "").strip()
    return text or None


def _bind_spend_context(
    request: Request,
    ctx: Any,
    *,
    model: str,
    client_id: str | None,
) -> None:
    router = getattr(ctx, "router", None)
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
    settings = getattr(ctx, "settings", None)
    usage = getattr(settings, "usage", None)
    fallback = float(getattr(usage, "frontier_price_per_1k_tokens", 0.002) or 0.002)
    pricing = getattr(router, "pricing", None)
    if pricing is None and settings is not None:
        pricing = getattr(settings, "pricing", None)
    bind_spend_context(
        SpendContext(
            key_id=key_id,
            team_id=team_id,
            client_id=client_id or "",
            request_id=str(getattr(request.state, "request_id", None) or ""),
            requested_model=model,
            pricing=pricing,
            fallback_per_1k=fallback,
        )
    )


def _record_request(
    ctx: Any,
    *,
    client_id: str | None,
    model: str,
    query: str,
    documents: list[str],
) -> None:
    ledger = getattr(getattr(ctx, "router", None), "usage_ledger", None)
    search_units = len(documents)
    prompt_chars = len(query) + sum(len(doc) for doc in documents)
    metrics = getattr(ctx, "metrics", None)
    if metrics is not None:
        metrics.record(
            "rerank",
            cache_hit=False,
            modality="rerank",
            input_tokens=search_units,
            output_tokens=0,
        )
    if ledger is None:
        return
    ledger.record(
        tier="rerank",
        cache_hit=False,
        prompt_chars=prompt_chars,
        completion_chars=0,
        client_id=client_id,
        model=model,
        provider="rerank",
        input_tokens=search_units,
        output_tokens=0,
    )


async def handle_rerank(request: Request, body: RerankRequest) -> Any:
    from daari.gateway.idempotency import (
        abandon_slot,
        complete_json_slot,
        resolve_idempotency,
    )
    from daari.gateway.model_access import reject_disallowed_model, reject_frontier_passthrough

    blocked = reject_frontier_passthrough(request)
    if blocked is not None:
        return blocked

    ctx = request.app.state.ctx
    settings = ctx.settings

    idem_kind, idem_response, idem_slot = await resolve_idempotency(request, ctx, body)
    if idem_kind in {"replay", "conflict"} and idem_response is not None:
        return idem_response

    pin = region_pin_from_request(request)
    try:
        targets = resolve_l6_targets(
            settings, region_pin=pin, default_model="rerank-english-v3.0"
        )
    except RegionUnavailable as exc:
        log_gateway_event("rerank_region_unavailable", {"pin": exc.pin})
        abandon_slot(idem_slot)
        return _error(400, "region_unavailable", str(exc))
    if not targets:
        log_gateway_event("rerank_unavailable", {"reason": "frontier_disabled_or_no_key"})
        abandon_slot(idem_slot)
        return _error(501, "not_implemented", _UNAVAILABLE)

    try:
        documents = normalize_documents(body.documents)
    except ValueError as exc:
        abandon_slot(idem_slot)
        return _error(400, "invalid_request", str(exc))
    if not documents:
        abandon_slot(idem_slot)
        return _error(400, "invalid_request", "documents must be a non-empty list")

    model = (body.model or "").strip() or targets[0].default_model
    denied = reject_disallowed_model(request, model, settings)
    if denied is not None:
        abandon_slot(idem_slot)
        return denied

    from daari.gateway.guardrails import (
        apply_endpoint_input_policy,
        endpoint_guardrail_blocked_response,
        router_guardrails,
    )

    engine = router_guardrails(ctx)
    metrics = getattr(ctx, "metrics", None)
    query_policy = apply_endpoint_input_policy(body.query, engine, metrics=metrics)
    if query_policy.blocked:
        abandon_slot(idem_slot)
        return endpoint_guardrail_blocked_response(query_policy.block_message)
    scrubbed_docs: list[str] = []
    for doc in documents:
        doc_policy = apply_endpoint_input_policy(doc, engine, metrics=metrics)
        if doc_policy.blocked:
            abandon_slot(idem_slot)
            return endpoint_guardrail_blocked_response(doc_policy.block_message)
        scrubbed_docs.append(doc_policy.text)
    documents = scrubbed_docs
    query = query_policy.text

    payload: dict[str, Any] = {
        "model": model,
        "query": query,
        "documents": documents,
    }
    if body.top_n is not None:
        payload["top_n"] = body.top_n

    retry_settings = getattr(getattr(settings, "upstream", None), "retry", None)
    last_exc: Exception | None = None
    last_upstream: httpx.Response | None = None

    for target in targets:
        headers = {
            "Authorization": f"Bearer {target.api_key}",
            "Content-Type": "application/json",
        }
        url = f"{target.base_url}/rerank"
        try:
            upstream = await post_rerank(
                url,
                headers=headers,
                payload=payload,
                timeout=target.timeout,
                retry=target.retry if target.retry is not None else retry_settings,
                metrics=metrics,
            )
        except httpx.HTTPStatusError as exc:
            last_upstream = exc.response
            last_exc = exc
            log_gateway_event(
                "rerank_slot_error",
                {
                    "slot": target.slot_id,
                    "error": summarize_upstream_failure(exc),
                    "status": exc.response.status_code if exc.response is not None else None,
                },
            )
            continue
        except Exception as exc:
            last_exc = exc
            log_gateway_event(
                "rerank_slot_error",
                {"slot": target.slot_id, "error": summarize_upstream_failure(exc)},
            )
            continue
        if is_slot_failure(upstream):
            last_upstream = upstream
            log_gateway_event(
                "rerank_slot_http",
                {"slot": target.slot_id, "status": upstream.status_code},
            )
            continue
        if upstream.status_code >= 400:
            log_gateway_event("rerank_upstream_http", {"status": upstream.status_code})
            try:
                detail = upstream.json()
            except Exception:
                detail = {"error": {"type": "upstream_error", "message": upstream.text[:200]}}
            abandon_slot(idem_slot)
            return JSONResponse(status_code=upstream.status_code, content=detail)
        try:
            data = upstream.json()
        except Exception:
            abandon_slot(idem_slot)
            return _error(502, "bad_gateway", "Rerank upstream returned non-JSON.")
        log_gateway_event(
            "rerank_ok", {"model": model, "docs": len(documents), "slot": target.slot_id}
        )
        caller = _caller_client_id(request)
        _bind_spend_context(request, ctx, model=model, client_id=caller)
        _record_request(
            ctx,
            client_id=caller,
            model=model,
            query=query,
            documents=documents,
        )
        from daari.gateway.cost_headers import modality_response_headers, session_id_from_request

        prompt_chars = len(query) + sum(len(doc) for doc in documents)
        headers = modality_response_headers(
            ctx.settings,
            tier="rerank",
            model=model,
            prompt_chars=prompt_chars,
            input_tokens=len(documents),
            output_tokens=0,
            session_id=session_id_from_request(request),
            savings=getattr(getattr(ctx, "router", None), "session_savings", None),
        )
        complete_json_slot(idem_slot, status_code=200, payload=data)
        return JSONResponse(data, headers=headers)

    if last_upstream is not None:
        log_gateway_event("rerank_upstream_http", {"status": last_upstream.status_code})
        try:
            detail = last_upstream.json()
        except Exception:
            detail = {
                "error": {
                    "type": "upstream_error",
                    "message": (last_upstream.text or "")[:200],
                }
            }
        abandon_slot(idem_slot)
        return JSONResponse(status_code=last_upstream.status_code, content=detail)
    if last_exc is not None:
        log_gateway_event(
            "rerank_upstream_error",
            {"error": summarize_upstream_failure(last_exc)},
        )
    abandon_slot(idem_slot)
    return _error(503, "upstream_error", "Rerank upstream request failed.")
