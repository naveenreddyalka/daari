"""POST /v1/images/generations — OpenAI-shaped L6 passthrough with governance (#1064)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

import httpx
from fastapi import Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from daari.gateway.client_errors import request_deadline_response, summarize_upstream_failure
from daari.gateway.l6_passthrough import (
    FrontierBindingError,
    L6Target,
    RegionUnavailable,
    frontier_binding_error_response,
    frontier_binding_from_request,
    is_slot_failure,
    post_l6,
    region_pin_from_request,
    resolve_l6_targets,
)
from daari.gateway.request_log import log_gateway_event
from daari.router.deadline import (
    RequestDeadlineExceeded,
    bind_request_deadline,
    deadline_active,
    nonstream_timeout,
    parse_deadline_ms,
    resolve_deadline_seconds,
)

_UNAVAILABLE = (
    "Image generation requires a configured frontier (L6) OpenAI-compatible "
    "endpoint. Set frontier.enabled=true and provide an API key; daari does "
    "not invent images locally."
)

# Image-input token rate ($/1M) when usage.input_tokens_details splits text vs
# image. Catalog input_per_1m is the text rate (#2249 / OpenAI pricing page).
_IMAGE_INPUT_PER_1M: dict[str, float] = {
    "gpt-image-2.6-sunburst": 8.0,
    "gpt-image-2.6-flare": 8.0,
    "gpt-image-2.5-sunburst": 8.0,
    "gpt-image-2.5-flare": 8.0,
    "gpt-image-2": 8.0,
    "gpt-image-1.5": 8.0,
    "gpt-image-1": 8.0,
    "gpt-image-1-mini": 2.5,
}

# Documented per-image USD when upstream omits usage (dall-e-2/3 era).
# Sources: OpenAI Images pricing (standard 1024×1024).
_PER_IMAGE_ESTIMATE_USD = 0.04
_PER_IMAGE_ESTIMATE_BY_MODEL: dict[str, float] = {
    "dall-e-3": 0.04,
    "dall-e-2": 0.02,
}
_DALL_E_3_HD_USD = 0.08

ImagesTarget = L6Target

_http: httpx.AsyncClient | None = None


@dataclass(frozen=True)
class ImageCharge:
    input_tokens: int
    output_tokens: int
    cost_usd: float
    estimated: bool


def images_default_model(settings: Any) -> str:
    """Configurable default for /v1/images/* when the client omits model (#2249)."""
    frontier = getattr(settings, "frontier", None)
    configured = str(getattr(frontier, "images_default_model", "") or "").strip()
    return configured or "gpt-image-2.6-flare"


def _per_image_estimate_usd(model: str, *, quality: str | None = None) -> float:
    name = (model or "").strip().lower()
    if "dall-e-3" in name:
        q = (quality or "standard").strip().lower()
        if q in {"hd", "high"}:
            return _DALL_E_3_HD_USD
        return _PER_IMAGE_ESTIMATE_BY_MODEL["dall-e-3"]
    for key, amount in _PER_IMAGE_ESTIMATE_BY_MODEL.items():
        if key in name:
            return amount
    return _PER_IMAGE_ESTIMATE_USD


def _image_input_rate(model: str, text_input_per_1m: float) -> float:
    from daari.pricing import matching_model_key

    key = matching_model_key(model, _IMAGE_INPUT_PER_1M)
    if key is not None:
        return float(_IMAGE_INPUT_PER_1M[key])
    return float(text_input_per_1m)


def _tokens_from_usage(usage: dict[str, Any]) -> tuple[int, int]:
    raw_in = usage.get("input_tokens", usage.get("prompt_tokens"))
    raw_out = usage.get("output_tokens", usage.get("completion_tokens"))
    inp = int(raw_in) if isinstance(raw_in, (int, float)) and raw_in >= 0 else 0
    out = int(raw_out) if isinstance(raw_out, (int, float)) and raw_out >= 0 else 0
    return inp, out


def price_image_request(
    model: str,
    upstream: dict[str, Any] | None,
    *,
    n: int,
    quality: str | None = None,
    pricing: Any = None,
    fallback_per_1k: float = 0.002,
) -> ImageCharge:
    """Bill from upstream ``usage`` or a documented per-image estimate (#2249)."""
    from daari.pricing import cost_usd, resolve_price

    count = max(1, int(n or 1))
    usage = None
    if isinstance(upstream, dict) and isinstance(upstream.get("usage"), dict):
        usage = upstream["usage"]
    if usage is not None:
        inp, out = _tokens_from_usage(usage)
        details = usage.get("input_tokens_details")
        details = details if isinstance(details, dict) else {}
        text_raw = details.get("text_tokens")
        image_raw = details.get("image_tokens")
        has_split = isinstance(text_raw, (int, float)) or isinstance(image_raw, (int, float))
        if has_split:
            text_tok = int(text_raw) if isinstance(text_raw, (int, float)) and text_raw >= 0 else 0
            image_tok = (
                int(image_raw) if isinstance(image_raw, (int, float)) and image_raw >= 0 else 0
            )
            price = resolve_price(model, pricing, fallback_per_1k=fallback_per_1k)
            image_rate = _image_input_rate(model, price.input_per_1m)
            cost = (
                text_tok / 1_000_000 * float(price.input_per_1m)
                + image_tok / 1_000_000 * float(image_rate)
                + max(0, out) / 1_000_000 * float(price.output_per_1m)
            )
            return ImageCharge(
                input_tokens=max(inp, text_tok + image_tok),
                output_tokens=out,
                cost_usd=round(max(0.0, cost), 8),
                estimated=False,
            )
        if inp or out or "input_tokens" in usage or "prompt_tokens" in usage:
            cost = cost_usd(
                model,
                inp,
                out,
                pricing,
                fallback_per_1k=fallback_per_1k,
            )
            return ImageCharge(
                input_tokens=inp,
                output_tokens=out,
                cost_usd=round(max(0.0, cost), 8),
                estimated=False,
            )
    unit = _per_image_estimate_usd(model, quality=quality)
    cost = round(unit * count, 8)
    log_gateway_event(
        "images_cost_estimated",
        {
            "model": model,
            "n": count,
            "quality": (quality or "") or None,
            "per_image_usd": unit,
            "cost_usd": cost,
        },
    )
    return ImageCharge(
        input_tokens=count,
        output_tokens=0,
        cost_usd=cost,
        estimated=True,
    )


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
            settings,
            region_pin=region_pin,
            default_model=images_default_model(settings),
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


async def post_images_multipart(
    url: str,
    *,
    headers: dict[str, str],
    form: dict[str, str],
    files: dict[str, tuple[str, bytes, str]],
    timeout: float,
    retry: Any | None = None,
    metrics: Any | None = None,
) -> httpx.Response:
    """Multipart POST for /images/edits (and similar) with retry (#1097)."""
    from daari.router.retry import RetryPolicy, is_retryable_status, run_upstream

    policy = (
        retry
        if isinstance(retry, RetryPolicy)
        else (RetryPolicy(attempts=1) if retry is None else RetryPolicy.from_settings(retry))
    )

    async def attempt() -> httpx.Response:
        response = await _shared_client().post(
            url, headers=headers, data=form, files=files, timeout=timeout
        )
        if is_retryable_status(
            response.status_code, failover_on_http_5xx=policy.failover_on_http_5xx
        ):
            response.raise_for_status()
        return response

    return await run_upstream(
        attempt,
        upstream="images",
        policy=policy,
        timeout=timeout,
        metrics=metrics,
    )


def _images_deadline_seconds(request: Request, settings: Any) -> float | None:
    header_ms = parse_deadline_ms(request.headers.get("x-daari-deadline-ms"))
    upstream = getattr(settings, "upstream", None)
    setting = getattr(upstream, "request_deadline_seconds", None) if upstream else None
    return resolve_deadline_seconds(header_ms, setting)


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
    user_id: str | None = None,
    reported_cost: float | None = None,
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
            user_id=(user_id or "").strip(),
            request_id=str(getattr(request.state, "request_id", None) or ""),
            requested_model=model,
            pricing=pricing,
            fallback_per_1k=fallback,
            reported_cost=reported_cost,
        )
    )


def _record_request(
    ctx: Any,
    *,
    client_id: str | None,
    model: str,
    prompt: str,
    n: int,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    reported_cost: float | None = None,
) -> None:
    tokens_in = max(1, n) if input_tokens is None else max(0, int(input_tokens))
    tokens_out = 0 if output_tokens is None else max(0, int(output_tokens))
    metrics = getattr(ctx, "metrics", None)
    if metrics is not None:
        metrics.record(
            "images",
            cache_hit=False,
            modality="images",
            input_tokens=tokens_in,
            output_tokens=tokens_out,
        )
    ledger = getattr(getattr(ctx, "router", None), "usage_ledger", None)
    if ledger is None:
        return
    # Record as L6 so per-key/team frontier budgets meter image spend like chat
    # (#2249). Metrics keep modality="images" above.
    ledger.record(
        tier="L6",
        cache_hit=False,
        prompt_chars=len(prompt),
        completion_chars=0,
        client_id=client_id,
        model=model,
        provider="images",
        input_tokens=tokens_in,
        output_tokens=tokens_out,
        reported_cost=reported_cost,
    )


def _charge_for(
    ctx: Any,
    *,
    model: str,
    upstream: dict[str, Any],
    n: int,
    quality: str | None = None,
) -> ImageCharge:
    settings = getattr(ctx, "settings", None)
    usage = getattr(settings, "usage", None) if settings is not None else None
    fallback = float(getattr(usage, "frontier_price_per_1k_tokens", 0.002) or 0.002)
    router = getattr(ctx, "router", None)
    pricing = getattr(router, "pricing", None) if router is not None else None
    if pricing is None and settings is not None:
        pricing = getattr(settings, "pricing", None)
    return price_image_request(
        model,
        upstream,
        n=n,
        quality=quality,
        pricing=pricing,
        fallback_per_1k=fallback,
    )


async def handle_images_generations(
    request: Request, body: ImagesGenerationsRequest
) -> Any:
    from daari.gateway.idempotency import (
        abandon_slot,
        complete_json_slot,
        resolve_idempotency,
    )
    from daari.gateway.model_access import (
        reject_disallowed_model,
        reject_frontier_passthrough,
        reject_retired_model,
    )

    blocked = reject_frontier_passthrough(request)
    if blocked is not None:
        return blocked

    prompt = (body.prompt or "").strip()
    if not prompt:
        return _error(400, "invalid_request_error", "prompt is required")

    ctx = request.app.state.ctx
    settings = ctx.settings
    seconds = _images_deadline_seconds(request, settings)
    if seconds is not None and not deadline_active():
        try:
            with bind_request_deadline(seconds, metrics=ctx.metrics):
                return await handle_images_generations(request, body)
        except RequestDeadlineExceeded as exc:
            return request_deadline_response(exc)

    idem_kind, idem_response, idem_slot = await resolve_idempotency(request, ctx, body)
    if idem_kind in {"replay", "conflict"} and idem_response is not None:
        return idem_response

    pin = region_pin_from_request(request)
    default_model = images_default_model(settings)
    try:
        targets = resolve_l6_targets(
            settings,
            region_pin=pin,
            default_model=default_model,
            binding=frontier_binding_from_request(request),
        )
    except RegionUnavailable as exc:
        log_gateway_event("images_region_unavailable", {"pin": exc.pin})
        abandon_slot(idem_slot)
        return _error(400, "region_unavailable", str(exc))
    except FrontierBindingError as exc:
        log_gateway_event("images_frontier_binding_error", {"error": str(exc)})
        abandon_slot(idem_slot)
        return frontier_binding_error_response(exc)
    if not targets:
        log_gateway_event("images_unavailable", {"reason": "frontier_disabled_or_no_key"})
        abandon_slot(idem_slot)
        return _error(501, "not_implemented", _UNAVAILABLE)

    # Prefer explicit body.model, then images_default_model — not the chat
    # frontier provider model, which is often a text id (#2249).
    model = (body.model or "").strip() or default_model
    denied = reject_disallowed_model(request, model, settings)
    if denied is not None:
        abandon_slot(idem_slot)
        return denied
    retired = reject_retired_model(request, model, settings)
    if retired is not None:
        abandon_slot(idem_slot)
        return retired

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
            timeout = nonstream_timeout(target.timeout, "images")
            upstream = await post_images(
                url,
                headers=headers,
                payload=payload,
                timeout=timeout,
                retry=target.retry if target.retry is not None else retry_settings,
                metrics=metrics,
            )
        except RequestDeadlineExceeded as exc:
            abandon_slot(idem_slot)
            return request_deadline_response(exc)
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
        charge = _charge_for(
            ctx, model=model, upstream=data, n=n, quality=body.quality
        )
        _bind_spend_context(
            request,
            ctx,
            model=model,
            client_id=caller,
            user_id=body.user,
            reported_cost=charge.cost_usd,
        )
        _record_request(
            ctx,
            client_id=caller,
            model=model,
            prompt=prompt,
            n=n,
            input_tokens=charge.input_tokens,
            output_tokens=charge.output_tokens,
            reported_cost=charge.cost_usd,
        )
        from daari.gateway.cost_headers import modality_response_headers, session_id_from_request

        cost_headers = modality_response_headers(
            settings,
            tier="images",
            model=model,
            prompt_chars=len(prompt),
            input_tokens=charge.input_tokens,
            output_tokens=charge.output_tokens,
            cost_usd=charge.cost_usd,
            executor="frontier",
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


async def handle_images_edits(
    request: Request,
    *,
    image: Any,
    prompt: str,
    mask: Any | None = None,
    model: str = "",
    n: int | None = None,
    size: str | None = None,
    response_format: str | None = None,
    user: str | None = None,
) -> Any:
    """POST /v1/images/edits — multipart L6 passthrough (#1097)."""
    from daari.gateway.model_access import (
        reject_disallowed_model,
        reject_frontier_passthrough,
        reject_retired_model,
    )

    blocked = reject_frontier_passthrough(request)
    if blocked is not None:
        return blocked

    prompt_text = (prompt or "").strip()
    if not prompt_text:
        return _error(400, "invalid_request_error", "prompt is required")
    if image is None:
        return _error(400, "invalid_request_error", "image is required")

    ctx = request.app.state.ctx
    settings = ctx.settings
    seconds = _images_deadline_seconds(request, settings)
    if seconds is not None and not deadline_active():
        try:
            with bind_request_deadline(seconds, metrics=ctx.metrics):
                return await handle_images_edits(
                    request,
                    image=image,
                    prompt=prompt,
                    mask=mask,
                    model=model,
                    n=n,
                    size=size,
                    response_format=response_format,
                    user=user,
                )
        except RequestDeadlineExceeded as exc:
            return request_deadline_response(exc)

    async def _read_upload(upload: Any) -> tuple[bytes, str, str]:
        read = getattr(upload, "read", None)
        raw = await read() if callable(read) else bytes(upload or b"")
        name = str(getattr(upload, "filename", None) or "image.png").strip() or "image.png"
        ctype = (
            str(getattr(upload, "content_type", None) or "application/octet-stream").strip()
            or "application/octet-stream"
        )
        return bytes(raw or b""), name, ctype

    image_bytes, image_name, image_type = await _read_upload(image)
    if not image_bytes:
        return _error(400, "invalid_request_error", "image is required")

    mask_bytes: bytes | None = None
    mask_name = "mask.png"
    mask_type = "application/octet-stream"
    if mask is not None:
        mask_bytes, mask_name, mask_type = await _read_upload(mask)
        if not mask_bytes:
            mask_bytes = None

    pin = region_pin_from_request(request)
    default_model = images_default_model(settings)
    try:
        targets = resolve_l6_targets(
            settings,
            region_pin=pin,
            default_model=default_model,
            binding=frontier_binding_from_request(request),
        )
    except RegionUnavailable as exc:
        log_gateway_event("images_edits_region_unavailable", {"pin": exc.pin})
        return _error(400, "region_unavailable", str(exc))
    except FrontierBindingError as exc:
        log_gateway_event("images_edits_frontier_binding_error", {"error": str(exc)})
        return frontier_binding_error_response(exc)
    if not targets:
        log_gateway_event("images_edits_unavailable", {"reason": "frontier_disabled_or_no_key"})
        return _error(501, "not_implemented", _UNAVAILABLE)

    resolved_model = (model or "").strip() or default_model
    denied = reject_disallowed_model(request, resolved_model, settings)
    if denied is not None:
        return denied
    retired = reject_retired_model(request, resolved_model, settings)
    if retired is not None:
        return retired

    from daari.gateway.guardrails import (
        apply_endpoint_input_policy,
        endpoint_guardrail_blocked_response,
        router_guardrails,
    )

    policy = apply_endpoint_input_policy(
        prompt_text, router_guardrails(ctx), metrics=getattr(ctx, "metrics", None)
    )
    if policy.blocked:
        return endpoint_guardrail_blocked_response(policy.block_message)
    prompt_text = policy.text

    count = int(n or 1)
    form: dict[str, str] = {
        "prompt": prompt_text,
        "model": resolved_model,
        "n": str(count),
    }
    if size:
        form["size"] = size
    if response_format:
        form["response_format"] = response_format

    files: dict[str, tuple[str, bytes, str]] = {
        "image": (image_name, image_bytes, image_type),
    }
    if mask_bytes is not None:
        files["mask"] = (mask_name, mask_bytes, mask_type)

    retry_settings = getattr(getattr(settings, "upstream", None), "retry", None)
    metrics = getattr(ctx, "metrics", None)
    last_exc: Exception | None = None
    last_upstream: httpx.Response | None = None

    for target in targets:
        headers = {"Authorization": f"Bearer {target.api_key}"}
        url = f"{target.base_url}/images/edits"
        try:
            timeout = nonstream_timeout(target.timeout, "images")
            upstream = await post_images_multipart(
                url,
                headers=headers,
                form=form,
                files=files,
                timeout=timeout,
                retry=target.retry if target.retry is not None else retry_settings,
                metrics=metrics,
            )
        except RequestDeadlineExceeded as exc:
            return request_deadline_response(exc)
        except httpx.HTTPStatusError as exc:
            last_upstream = exc.response
            last_exc = exc
            log_gateway_event(
                "images_edits_slot_error",
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
                "images_edits_slot_error",
                {
                    "slot": target.slot_id,
                    "error": summarize_upstream_failure(exc),
                },
            )
            continue
        if is_slot_failure(upstream):
            last_upstream = upstream
            log_gateway_event(
                "images_edits_slot_http",
                {"slot": target.slot_id, "status": upstream.status_code},
            )
            continue
        if upstream.status_code >= 400:
            log_gateway_event(
                "images_edits_upstream_http",
                {"status": upstream.status_code, "slot": target.slot_id},
            )
            try:
                detail = upstream.json()
            except Exception:
                detail = {"error": {"type": "upstream_error", "message": upstream.text[:200]}}
            return JSONResponse(status_code=upstream.status_code, content=detail)
        try:
            data = upstream.json()
        except Exception:
            return _error(502, "bad_gateway", "Images edits upstream returned non-JSON.")
        log_gateway_event(
            "images_edits_ok",
            {"model": resolved_model, "n": count, "slot": target.slot_id},
        )
        caller = _caller_client_id(request)
        charge = _charge_for(ctx, model=resolved_model, upstream=data, n=count)
        _bind_spend_context(
            request,
            ctx,
            model=resolved_model,
            client_id=caller,
            user_id=user,
            reported_cost=charge.cost_usd,
        )
        _record_request(
            ctx,
            client_id=caller,
            model=resolved_model,
            prompt=prompt_text,
            n=count,
            input_tokens=charge.input_tokens,
            output_tokens=charge.output_tokens,
            reported_cost=charge.cost_usd,
        )
        from daari.gateway.cost_headers import modality_response_headers, session_id_from_request

        cost_headers = modality_response_headers(
            settings,
            tier="images",
            model=resolved_model,
            prompt_chars=len(prompt_text),
            input_tokens=charge.input_tokens,
            output_tokens=charge.output_tokens,
            cost_usd=charge.cost_usd,
            executor="frontier",
            session_id=session_id_from_request(request),
            savings=getattr(getattr(ctx, "router", None), "session_savings", None),
        )
        return JSONResponse(data, headers=cost_headers)

    if last_upstream is not None:
        log_gateway_event(
            "images_edits_upstream_http",
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
        return JSONResponse(status_code=last_upstream.status_code, content=detail)
    if last_exc is not None:
        log_gateway_event(
            "images_edits_upstream_error",
            {"error": summarize_upstream_failure(last_exc)},
        )
    return _error(503, "upstream_error", "Images edits upstream request failed.")


async def handle_images_variations(
    request: Request,
    *,
    image: Any,
    model: str = "",
    n: int | None = None,
    size: str | None = None,
    response_format: str | None = None,
    user: str | None = None,
) -> Any:
    """POST /v1/images/variations — multipart L6 passthrough (#1098)."""
    from daari.gateway.model_access import (
        reject_disallowed_model,
        reject_frontier_passthrough,
        reject_retired_model,
    )

    blocked = reject_frontier_passthrough(request)
    if blocked is not None:
        return blocked

    if image is None:
        return _error(400, "invalid_request_error", "image is required")

    ctx = request.app.state.ctx
    settings = ctx.settings
    seconds = _images_deadline_seconds(request, settings)
    if seconds is not None and not deadline_active():
        try:
            with bind_request_deadline(seconds, metrics=ctx.metrics):
                return await handle_images_variations(
                    request,
                    image=image,
                    model=model,
                    n=n,
                    size=size,
                    response_format=response_format,
                    user=user,
                )
        except RequestDeadlineExceeded as exc:
            return request_deadline_response(exc)

    async def _read_upload(upload: Any) -> tuple[bytes, str, str]:
        read = getattr(upload, "read", None)
        raw = await read() if callable(read) else bytes(upload or b"")
        name = str(getattr(upload, "filename", None) or "image.png").strip() or "image.png"
        ctype = (
            str(getattr(upload, "content_type", None) or "application/octet-stream").strip()
            or "application/octet-stream"
        )
        return bytes(raw or b""), name, ctype

    image_bytes, image_name, image_type = await _read_upload(image)
    if not image_bytes:
        return _error(400, "invalid_request_error", "image is required")

    pin = region_pin_from_request(request)
    default_model = images_default_model(settings)
    try:
        targets = resolve_l6_targets(
            settings,
            region_pin=pin,
            default_model=default_model,
            binding=frontier_binding_from_request(request),
        )
    except RegionUnavailable as exc:
        log_gateway_event("images_variations_region_unavailable", {"pin": exc.pin})
        return _error(400, "region_unavailable", str(exc))
    except FrontierBindingError as exc:
        log_gateway_event("images_variations_frontier_binding_error", {"error": str(exc)})
        return frontier_binding_error_response(exc)
    if not targets:
        log_gateway_event(
            "images_variations_unavailable", {"reason": "frontier_disabled_or_no_key"}
        )
        return _error(501, "not_implemented", _UNAVAILABLE)

    resolved_model = (model or "").strip() or default_model
    denied = reject_disallowed_model(request, resolved_model, settings)
    if denied is not None:
        return denied
    retired = reject_retired_model(request, resolved_model, settings)
    if retired is not None:
        return retired

    count = int(n or 1)
    form: dict[str, str] = {
        "model": resolved_model,
        "n": str(count),
    }
    if size:
        form["size"] = size
    if response_format:
        form["response_format"] = response_format

    files: dict[str, tuple[str, bytes, str]] = {
        "image": (image_name, image_bytes, image_type),
    }

    retry_settings = getattr(getattr(settings, "upstream", None), "retry", None)
    metrics = getattr(ctx, "metrics", None)
    last_exc: Exception | None = None
    last_upstream: httpx.Response | None = None

    for target in targets:
        headers = {"Authorization": f"Bearer {target.api_key}"}
        url = f"{target.base_url}/images/variations"
        try:
            timeout = nonstream_timeout(target.timeout, "images")
            upstream = await post_images_multipart(
                url,
                headers=headers,
                form=form,
                files=files,
                timeout=timeout,
                retry=target.retry if target.retry is not None else retry_settings,
                metrics=metrics,
            )
        except RequestDeadlineExceeded as exc:
            return request_deadline_response(exc)
        except httpx.HTTPStatusError as exc:
            last_upstream = exc.response
            last_exc = exc
            log_gateway_event(
                "images_variations_slot_error",
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
                "images_variations_slot_error",
                {
                    "slot": target.slot_id,
                    "error": summarize_upstream_failure(exc),
                },
            )
            continue
        if is_slot_failure(upstream):
            last_upstream = upstream
            log_gateway_event(
                "images_variations_slot_http",
                {"slot": target.slot_id, "status": upstream.status_code},
            )
            continue
        if upstream.status_code >= 400:
            log_gateway_event(
                "images_variations_upstream_http",
                {"status": upstream.status_code, "slot": target.slot_id},
            )
            try:
                detail = upstream.json()
            except Exception:
                detail = {"error": {"type": "upstream_error", "message": upstream.text[:200]}}
            return JSONResponse(status_code=upstream.status_code, content=detail)
        try:
            data = upstream.json()
        except Exception:
            return _error(502, "bad_gateway", "Images variations upstream returned non-JSON.")
        log_gateway_event(
            "images_variations_ok",
            {"model": resolved_model, "n": count, "slot": target.slot_id},
        )
        caller = _caller_client_id(request)
        charge = _charge_for(ctx, model=resolved_model, upstream=data, n=count)
        _bind_spend_context(
            request,
            ctx,
            model=resolved_model,
            client_id=caller,
            user_id=user,
            reported_cost=charge.cost_usd,
        )
        _record_request(
            ctx,
            client_id=caller,
            model=resolved_model,
            prompt="",
            n=count,
            input_tokens=charge.input_tokens,
            output_tokens=charge.output_tokens,
            reported_cost=charge.cost_usd,
        )
        from daari.gateway.cost_headers import modality_response_headers, session_id_from_request

        cost_headers = modality_response_headers(
            settings,
            tier="images",
            model=resolved_model,
            prompt_chars=0,
            input_tokens=charge.input_tokens,
            output_tokens=charge.output_tokens,
            cost_usd=charge.cost_usd,
            executor="frontier",
            session_id=session_id_from_request(request),
            savings=getattr(getattr(ctx, "router", None), "session_savings", None),
        )
        return JSONResponse(data, headers=cost_headers)

    if last_upstream is not None:
        log_gateway_event(
            "images_variations_upstream_http",
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
        return JSONResponse(status_code=last_upstream.status_code, content=detail)
    if last_exc is not None:
        log_gateway_event(
            "images_variations_upstream_error",
            {"error": summarize_upstream_failure(last_exc)},
        )
    return _error(503, "upstream_error", "Images variations upstream request failed.")
