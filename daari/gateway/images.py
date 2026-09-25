"""POST /v1/images/generations — OpenAI-shaped L6 passthrough with governance (#1064)."""

from __future__ import annotations

from typing import Any, Literal

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
    "Image generation requires a configured frontier (L6) OpenAI-compatible "
    "endpoint. Set frontier.enabled=true and provide an API key; daari does "
    "not invent images locally."
)

ImagesTarget = L6Target

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


class ImagesGenerationsRequest(BaseModel):
    prompt: str
    model: str | None = Field(default=None)
    n: int | None = Field(default=None, ge=1, le=10)
    size: str | None = Field(default=None)
    quality: str | None = Field(default=None)
    response_format: Literal["url", "b64_json"] | None = Field(default=None)
    user: str | None = Field(default=None)


def _error(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"error": {"type": code, "message": message}},
    )


def resolve_images_target(
    settings: Any, *, region_pin: str | None = None
) -> ImagesTarget | None:
    """First eligible frontier slot (or None). Prefer resolve_l6_targets for failover."""
    try:
        targets = resolve_l6_targets(
            settings, region_pin=region_pin, default_model="dall-e-3"
        )
    except RegionUnavailable:
        return None
    return targets[0] if targets else None


async def post_images(
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
        upstream="images",
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
            reported_cost=0.0,
        )
    )


def _record_request(
    ctx: Any,
    *,
    client_id: str | None,
    model: str,
    prompt: str,
    n: int,
) -> None:
    ledger = getattr(getattr(ctx, "router", None), "usage_ledger", None)
    if ledger is None:
        return
    ledger.record(
        tier="images",
        cache_hit=False,
        prompt_chars=len(prompt),
        completion_chars=0,
        client_id=client_id,
        model=model,
        provider="images",
        input_tokens=max(1, n),
        output_tokens=0,
        reported_cost=0.0,
    )


async def handle_images_generations(
    request: Request, body: ImagesGenerationsRequest
) -> Any:
    from daari.gateway.idempotency import (
        abandon_slot,
        complete_json_slot,
        resolve_idempotency,
    )
    from daari.gateway.model_access import reject_disallowed_model, reject_frontier_passthrough

    blocked = reject_frontier_passthrough(request)
    if blocked is not None:
        return blocked

    prompt = (body.prompt or "").strip()
    if not prompt:
        return _error(400, "invalid_request_error", "prompt is required")

    ctx = request.app.state.ctx
    settings = ctx.settings

    idem_kind, idem_response, idem_slot = await resolve_idempotency(request, ctx, body)
    if idem_kind in {"replay", "conflict"} and idem_response is not None:
        return idem_response

    pin = region_pin_from_request(request)
    try:
        targets = resolve_l6_targets(
            settings, region_pin=pin, default_model="dall-e-3"
        )
    except RegionUnavailable as exc:
        log_gateway_event("images_region_unavailable", {"pin": exc.pin})
        abandon_slot(idem_slot)
        return _error(400, "region_unavailable", str(exc))
    if not targets:
        log_gateway_event("images_unavailable", {"reason": "frontier_disabled_or_no_key"})
        abandon_slot(idem_slot)
        return _error(501, "not_implemented", _UNAVAILABLE)

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

    policy = apply_endpoint_input_policy(
        prompt, router_guardrails(ctx), metrics=getattr(ctx, "metrics", None)
    )
    if policy.blocked:
        abandon_slot(idem_slot)
        return endpoint_guardrail_blocked_response(policy.block_message)
    if policy.text != prompt:
        prompt = policy.text
        body = ImagesGenerationsRequest(
            prompt=prompt,
            model=body.model,
            n=body.n,
            size=body.size,
            quality=body.quality,
            response_format=body.response_format,
            user=body.user,
        )

    n = int(body.n or 1)
    payload: dict[str, Any] = {"prompt": prompt, "model": model, "n": n}
    if body.size:
        payload["size"] = body.size
    if body.quality:
        payload["quality"] = body.quality
    if body.response_format:
        payload["response_format"] = body.response_format
    if body.user:
        payload["user"] = body.user

    retry_settings = getattr(getattr(settings, "upstream", None), "retry", None)
    metrics = getattr(ctx, "metrics", None)
    last_exc: Exception | None = None
    last_upstream: httpx.Response | None = None

    for target in targets:
        headers = {
            "Authorization": f"Bearer {target.api_key}",
            "Content-Type": "application/json",
        }
        url = f"{target.base_url}/images/generations"
        try:
            upstream = await post_images(
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
                "images_slot_error",
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
                "images_slot_error",
                {
                    "slot": target.slot_id,
                    "error": summarize_upstream_failure(exc),
                },
            )
            continue
        if is_slot_failure(upstream):
            last_upstream = upstream
            log_gateway_event(
                "images_slot_http",
                {"slot": target.slot_id, "status": upstream.status_code},
            )
            continue
        if upstream.status_code >= 400:
            log_gateway_event(
                "images_upstream_http",
                {"status": upstream.status_code, "slot": target.slot_id},
            )
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
            return _error(502, "bad_gateway", "Images upstream returned non-JSON.")
        log_gateway_event("images_ok", {"model": model, "n": n, "slot": target.slot_id})
        caller = _caller_client_id(request)
        _bind_spend_context(request, ctx, model=model, client_id=caller)
        _record_request(ctx, client_id=caller, model=model, prompt=prompt, n=n)
        from daari.gateway.cost_headers import modality_response_headers, session_id_from_request

        cost_headers = modality_response_headers(
            settings,
            tier="images",
            model=model,
            prompt_chars=len(prompt),
            input_tokens=max(1, n),
            output_tokens=0,
            cost_usd=0.0,
            session_id=session_id_from_request(request),
            savings=getattr(getattr(ctx, "router", None), "session_savings", None),
        )
        complete_json_slot(idem_slot, status_code=200, payload=data)
        return JSONResponse(data, headers=cost_headers)

    if last_upstream is not None:
        log_gateway_event(
            "images_upstream_http",
            {"status": last_upstream.status_code},
        )
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
            "images_upstream_error",
            {"error": summarize_upstream_failure(last_exc)},
        )
    abandon_slot(idem_slot)
    return _error(503, "upstream_error", "Images upstream request failed.")
