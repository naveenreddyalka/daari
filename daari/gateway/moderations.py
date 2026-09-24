"""POST /v1/moderations — OpenAI-shaped L6 passthrough (#1050, #1058)."""

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
    "Moderations require a configured frontier (L6) OpenAI-compatible endpoint. "
    "Set frontier.enabled=true and provide an API key; daari never invents "
    "classification scores locally."
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
class ModerationsTarget:
    base_url: str
    api_key: str
    default_model: str
    timeout: float


class ModerationsRequest(BaseModel):
    input: str | list[str]
    model: str | None = Field(default=None)


def _error(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"error": {"type": code, "message": message}},
    )


def resolve_moderations_target(settings: Any) -> ModerationsTarget | None:
    """Frontier L6 only — never invent local moderation scores."""
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
        model = str(getattr(frontier, "model", "") or "").strip() or "omni-moderation-latest"
    return ModerationsTarget(
        base_url=slot_base,
        api_key=secret,
        default_model=model,
        timeout=timeout,
    )


async def post_moderations(
    url: str,
    *,
    headers: dict[str, str],
    payload: dict[str, Any],
    timeout: float,
) -> httpx.Response:
    return await _shared_client().post(url, headers=headers, json=payload, timeout=timeout)


def _caller_client_id(request: Request) -> str | None:
    claims = getattr(request.state, "auth_claims", None)
    if claims is None or getattr(claims, "kind", None) != "virtual":
        return None
    client_id = getattr(claims, "client_id", None) or getattr(claims, "key_id", None)
    text = str(client_id or "").strip()
    return text or None


def _input_text(value: str | list[str]) -> str:
    if isinstance(value, list):
        return "\n".join(str(item) for item in value)
    return str(value)


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
            reported_cost=0.0,
        )
    )


def _record_request(
    ctx: Any,
    *,
    client_id: str | None,
    model: str,
    input_text: str,
) -> None:
    ledger = getattr(getattr(ctx, "router", None), "usage_ledger", None)
    if ledger is None:
        return
    ledger.record(
        tier="moderations",
        cache_hit=False,
        prompt_chars=len(input_text),
        completion_chars=0,
        client_id=client_id,
        model=model,
        provider="moderations",
        input_tokens=max(0, len(input_text) // 4),
        output_tokens=0,
        reported_cost=0.0,
    )


async def handle_moderations(request: Request, body: ModerationsRequest) -> Any:
    from daari.gateway.model_access import reject_disallowed_model, reject_frontier_passthrough

    blocked = reject_frontier_passthrough(request)
    if blocked is not None:
        return blocked

    ctx = request.app.state.ctx
    settings = ctx.settings
    target = resolve_moderations_target(settings)
    if target is None:
        log_gateway_event("moderations_unavailable", {"reason": "frontier_disabled_or_no_key"})
        return _error(501, "not_implemented", _UNAVAILABLE)

    model = (body.model or "").strip() or target.default_model
    denied = reject_disallowed_model(request, model, settings)
    if denied is not None:
        return denied

    from daari.gateway.guardrails import (
        apply_endpoint_input_policy,
        endpoint_guardrail_blocked_response,
        router_guardrails,
    )

    input_text = _input_text(body.input)
    policy = apply_endpoint_input_policy(
        input_text, router_guardrails(ctx), metrics=getattr(ctx, "metrics", None)
    )
    if policy.blocked:
        return endpoint_guardrail_blocked_response(policy.block_message)
    if policy.text != input_text:
        # Redact: rewrite list/string input to scrubbed form before upstream.
        if isinstance(body.input, list):
            body = ModerationsRequest(input=[policy.text], model=body.model)
        else:
            body = ModerationsRequest(input=policy.text, model=body.model)

    payload: dict[str, Any] = {"input": body.input, "model": model}
    headers = {
        "Authorization": f"Bearer {target.api_key}",
        "Content-Type": "application/json",
    }
    url = f"{target.base_url}/moderations"
    try:
        upstream = await post_moderations(
            url, headers=headers, payload=payload, timeout=target.timeout
        )
    except Exception as exc:
        log_gateway_event(
            "moderations_upstream_error",
            {"error": summarize_upstream_failure(exc)},
        )
        return _error(503, "upstream_error", "Moderations upstream request failed.")

    if upstream.status_code >= 400:
        log_gateway_event(
            "moderations_upstream_http",
            {"status": upstream.status_code},
        )
        try:
            detail = upstream.json()
        except Exception:
            detail = {"error": {"type": "upstream_error", "message": upstream.text[:200]}}
        return JSONResponse(status_code=upstream.status_code, content=detail)

    try:
        data = upstream.json()
    except Exception:
        return _error(502, "bad_gateway", "Moderations upstream returned non-JSON.")
    log_gateway_event("moderations_ok", {"model": model})
    caller = _caller_client_id(request)
    _bind_spend_context(request, ctx, model=model, client_id=caller)
    _record_request(ctx, client_id=caller, model=model, input_text=_input_text(body.input))
    return data
