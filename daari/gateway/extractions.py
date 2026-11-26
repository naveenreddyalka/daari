"""POST /v1/extractions — OpenRouter Extractions twin on local + frontier (#2271)."""

from __future__ import annotations

import time
from typing import Any, Literal

import httpx
from fastapi import Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from daari.gateway.client_errors import backend_unavailable_message, summarize_upstream_failure
from daari.gateway.decisions import (
    BUILTIN_LOCAL_MODELS,
    default_local_model,
    is_local_decisions_model,
    local_decisions_models,
)
from daari.gateway.l6_passthrough import (
    RegionUnavailable,
    is_slot_failure,
    post_l6,
    region_pin_from_request,
    resolve_l6_targets,
)
from daari.gateway.request_log import log_gateway_event
from daari.pricing import cost_usd

_FIELD_TYPES = frozenset(
    {
        "text",
        "number",
        "date",
        "time",
        "datetime",
        "duration",
        "list",
        "estimate",
        "forecast",
    }
)

_FRONTIER_EXTRACTION_MODELS = frozenset(
    {
        "cloudflare/clairic",
        "inception/mercury-decide",
        "inference-net/schematron-v2-small",
        "inference-net/schematron-v2-turbo",
        "liquid/d1.2",
        "liquid/d1.2-ultra",
        "perplexity/pplx-decider-v1.3",
        "perplexity/pplx-decider-flash-v1.3",
        "scaledown/extract",
    }
)

_ALLOWED_TOP = frozenset(
    {
        "model",
        "state",
        "fields",
        "assets",
        "reference_date",
        "provider",
        "user",
        "session_id",
        "trace",
    }
)

_UNAVAILABLE_LOCAL = (
    "Local extractions require Ollama / systemone with /v1/extractions "
    "and systemone.enabled=true. Start Ollama or set ollama.base_url."
)

_UNAVAILABLE_FRONTIER = (
    "Extractions for frontier models require a configured frontier (L6) "
    "OpenAI-compatible endpoint. Set frontier.enabled=true and provide an API key."
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


class ExtractionFieldSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal[
        "text",
        "number",
        "date",
        "time",
        "datetime",
        "duration",
        "list",
        "estimate",
        "forecast",
    ]
    instructions: str | None = None
    unit: str | None = None
    null_threshold: float | None = None
    integer: bool | None = None
    decimals: int | None = None
    items: str | None = None
    min: Any | None = None
    max: Any | None = None
    step: Any | None = None
    scale: str | None = None
    horizon: int | None = None
    interval: str | None = None

    @field_validator("type")
    @classmethod
    def _known_type(cls, value: str) -> str:
        if value not in _FIELD_TYPES:
            raise ValueError(f"Unknown field type {value!r}")
        return value


class ExtractionsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model: str | None = None
    state: Any | None = None
    fields: dict[str, ExtractionFieldSpec] = Field(min_length=1)
    assets: dict[str, Any] | None = None
    reference_date: str | None = None
    provider: Any | None = None
    user: str | None = None
    session_id: str | None = None
    trace: Any | None = None


def _error(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"error": {"type": code, "message": message}},
    )


def parse_extractions_body(raw: Any) -> ExtractionsRequest | JSONResponse:
    if not isinstance(raw, dict):
        return _error(400, "invalid_request", "Request body must be a JSON object.")
    unknown = sorted(set(raw) - _ALLOWED_TOP)
    if unknown:
        keys = ", ".join(unknown)
        if "questions" in unknown:
            return _error(
                400,
                "invalid_request",
                "Unknown top-level key 'questions': use 'fields' on "
                "POST /v1/extractions (Decisions questions are not valid here).",
            )
        return _error(
            400,
            "invalid_request",
            f"Unknown top-level key(s): {keys}.",
        )
    fields = raw.get("fields")
    if not isinstance(fields, dict) or not fields:
        return _error(
            400,
            "invalid_request",
            "fields: at least one field is required.",
        )
    for name, spec in fields.items():
        if not isinstance(spec, dict):
            return _error(
                400,
                "invalid_request",
                f"fields.{name}: field spec must be an object.",
            )
        ftype = spec.get("type")
        if ftype is None:
            return _error(
                400,
                "invalid_request",
                f"fields.{name}: type is required.",
            )
        if ftype not in _FIELD_TYPES:
            return _error(
                400,
                "invalid_request",
                f"fields.{name}: unknown field type {ftype!r}.",
            )
    try:
        return ExtractionsRequest.model_validate(raw)
    except ValidationError as exc:
        first = exc.errors()[0] if exc.errors() else {}
        loc = ".".join(str(part) for part in first.get("loc", ())) or "body"
        msg = first.get("msg") or "invalid request"
        return _error(400, "invalid_request", f"{loc}: {msg}")


def is_frontier_extractions_model(model: str) -> bool:
    name = (model or "").strip().lower()
    if not name:
        return False
    if name in _FRONTIER_EXTRACTION_MODELS:
        return True
    # Dated / vendor variants of known slugs.
    for known in _FRONTIER_EXTRACTION_MODELS:
        if name == known or name.startswith(f"{known}-") or name.startswith(f"{known}:"):
            return True
    return False


def normalize_extractions_model(model: str, *, settings: Any = None) -> str | None:
    name = (model or "").strip()
    if not name:
        return None
    if is_frontier_extractions_model(name):
        lower = name.lower()
        for known in sorted(_FRONTIER_EXTRACTION_MODELS, key=len, reverse=True):
            if lower == known or lower.startswith(f"{known}-") or lower.startswith(f"{known}:"):
                return known
        return lower
    if is_local_decisions_model(name, settings=settings):
        catalog = local_decisions_models(settings)
        candidates = []
        lowered = name.lower()
        no_tag = lowered.split(":", 1)[0]
        after_slash = no_tag.split("/")[-1]
        for item in (lowered, no_tag, after_slash):
            if item and item not in candidates:
                candidates.append(item)
        for local in sorted(catalog, key=len, reverse=True):
            for candidate in candidates:
                if candidate == local or candidate.startswith(f"{local}-"):
                    return local
        return candidates[-1] if candidates else None
    return None


def _elapsed_ms(started: float) -> int:
    elapsed = time.perf_counter() - started
    millis = int(elapsed * 1000)
    if millis <= 0 and elapsed > 0:
        return 1
    return max(0, millis)


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
            region_pin=region_pin_from_request(request),
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
    prompt_chars: int,
    input_tokens: int,
    output_tokens: int,
    latency_ms: int,
    provider: str,
    cost_usd_value: float,
    user_id: str | None = None,
    tier: str = "extractions",
) -> None:
    metrics = getattr(ctx, "metrics", None)
    if metrics is not None:
        metrics.record(
            tier,
            cache_hit=False,
            modality="extractions",
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=latency_ms,
        )
    ledger = getattr(getattr(ctx, "router", None), "usage_ledger", None)
    if ledger is None:
        return
    ledger.record(
        tier=tier,
        cache_hit=False,
        prompt_chars=prompt_chars,
        completion_chars=0,
        client_id=client_id,
        user_id=(user_id or "").strip() or None,
        model=model,
        provider=provider,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        reported_cost=float(cost_usd_value),
    )


def _frontier_extractions_url(base_url: str) -> str:
    base = (base_url or "").rstrip("/")
    if "openrouter.ai" in base:
        if base.endswith("/api/v1"):
            return f"{base[: -len('/api/v1')]}/api/alpha/extractions"
        if "/api/v1/" in base:
            return base.replace("/api/v1/", "/api/alpha/") + (
                "" if base.endswith("extractions") else "/extractions"
            )
        return f"{base}/api/alpha/extractions"
    return f"{base}/extractions"


def _request_payload(model: str, body: ExtractionsRequest) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": model,
        "fields": {
            name: spec.model_dump(exclude_none=True) for name, spec in body.fields.items()
        },
    }
    if body.state is not None:
        payload["state"] = body.state
    if body.assets is not None:
        payload["assets"] = body.assets
    if body.reference_date is not None:
        payload["reference_date"] = body.reference_date
    if body.provider is not None:
        payload["provider"] = body.provider
    if body.user is not None:
        payload["user"] = body.user
    if body.session_id is not None:
        payload["session_id"] = body.session_id
    if body.trace is not None:
        payload["trace"] = body.trace
    return payload


def _prompt_chars(body: ExtractionsRequest) -> int:
    try:
        import json

        return len(
            json.dumps(
                {"state": body.state, "fields": list(body.fields)},
                default=str,
            )
        )
    except Exception:
        return len(str(body.state or "")) + len(body.fields)


async def _handle_local(
    request: Request,
    body: ExtractionsRequest,
    *,
    model: str,
) -> Any:
    ctx = request.app.state.ctx
    settings = ctx.settings
    systemone = getattr(settings, "systemone", None)
    if systemone is not None and not bool(getattr(systemone, "enabled", True)):
        log_gateway_event("extractions_local_disabled", {})
        return _error(501, "not_implemented", _UNAVAILABLE_LOCAL)

    from daari.gateway.systemone import (
        explicit_systemone_base,
        resolve_systemone_base,
        systemone_auth_headers,
        systemone_override_unavailable,
    )

    explicit = explicit_systemone_base(settings)
    base = resolve_systemone_base(settings)
    if not base:
        log_gateway_event("extractions_local_unavailable", {"reason": "no_ollama_base_url"})
        return _error(503, "backend_unavailable", _UNAVAILABLE_LOCAL)

    from daari.gateway.model_access import (
        reject_disallowed_model,
        reject_end_user,
        reject_retired_model,
    )

    denied = reject_disallowed_model(request, model, settings)
    if denied is not None:
        return denied
    retired = reject_retired_model(request, model, settings)
    if retired is not None:
        return retired
    user_denied = reject_end_user(request, settings, body.user)
    if user_denied is not None:
        return user_denied

    started = time.perf_counter()
    payload = _request_payload(model, body)
    timeout = float(
        getattr(getattr(settings, "upstream", None), "local_timeout_seconds", 120.0) or 120.0
    )
    url = f"{base.rstrip('/')}/v1/extractions"
    headers = systemone_auth_headers(settings)
    try:
        upstream = await _shared_client().post(
            url, json=payload, timeout=timeout, headers=headers or None
        )
    except httpx.RequestError as exc:
        log_gateway_event(
            "extractions_local_down",
            {"error": summarize_upstream_failure(exc)},
        )
        if explicit:
            message = systemone_override_unavailable(explicit)
        else:
            message = backend_unavailable_message(exc) or _UNAVAILABLE_LOCAL
        return _error(503, "backend_unavailable", message)

    latency_ms = _elapsed_ms(started)
    if upstream.status_code >= 400:
        log_gateway_event("extractions_local_upstream_http", {"status": upstream.status_code})
        try:
            detail = upstream.json()
        except Exception:
            detail = {
                "error": {
                    "type": "upstream_error",
                    "message": (upstream.text or "")[:200],
                }
            }
        return JSONResponse(status_code=upstream.status_code, content=detail)

    try:
        data = upstream.json()
    except Exception:
        return _error(502, "bad_gateway", "Local extractions upstream returned non-JSON.")
    if not isinstance(data, dict):
        return _error(502, "bad_gateway", "Local extractions upstream returned non-object JSON.")

    usage = data.get("usage") if isinstance(data.get("usage"), dict) else {}
    try:
        input_tokens = int(usage.get("input_tokens") or 0)
    except (TypeError, ValueError):
        input_tokens = 0
    try:
        output_tokens = int(usage.get("output_tokens") or 0)
    except (TypeError, ValueError):
        output_tokens = 0
    prompt_chars = _prompt_chars(body)
    if input_tokens <= 0:
        input_tokens = max(0, prompt_chars // 4)

    resolved_model = str(data.get("model") or model)
    caller = _caller_client_id(request)
    _bind_spend_context(
        request, ctx, model=resolved_model, client_id=caller, user_id=body.user
    )
    _record_request(
        ctx,
        client_id=caller,
        model=resolved_model,
        prompt_chars=prompt_chars,
        input_tokens=input_tokens,
        output_tokens=max(0, output_tokens),
        latency_ms=latency_ms,
        provider="ollama",
        cost_usd_value=0.0,
        user_id=body.user,
        tier="local",
    )

    out = dict(data)
    out.setdefault("id", f"ext_local_{resolved_model}")
    out.setdefault("object", "extraction")
    out["model"] = resolved_model
    out["usage"] = {
        "input_tokens": input_tokens,
        "output_tokens": max(0, output_tokens),
    }
    out["daari_meta"] = {
        "tier": "local",
        "executor": "ollama",
        "provider_id": "ollama",
        "model": resolved_model,
        "latency_ms": latency_ms,
        "input_tokens": input_tokens,
        "output_tokens": max(0, output_tokens),
        "usage_estimated": not bool(usage.get("input_tokens")),
        "cache_hit": False,
        "cost_usd": 0.0,
    }
    log_gateway_event(
        "extractions_local_ok",
        {"model": resolved_model, "latency_ms": latency_ms},
    )
    from daari.gateway.cost_headers import modality_response_headers, session_id_from_request

    headers_out = modality_response_headers(
        settings,
        tier="local",
        model=resolved_model,
        prompt_chars=prompt_chars,
        input_tokens=input_tokens,
        output_tokens=max(0, output_tokens),
        cost_usd=0.0,
        session_id=session_id_from_request(request),
        savings=getattr(getattr(ctx, "router", None), "session_savings", None),
    )
    return JSONResponse(out, headers=headers_out)


async def _handle_frontier(
    request: Request,
    body: ExtractionsRequest,
    *,
    model: str,
) -> Any:
    from daari.gateway.model_access import (
        reject_disallowed_model,
        reject_end_user,
        reject_frontier_passthrough,
        reject_retired_model,
    )

    blocked = reject_frontier_passthrough(request)
    if blocked is not None:
        return blocked

    ctx = request.app.state.ctx
    settings = ctx.settings
    pin = region_pin_from_request(request)
    try:
        targets = resolve_l6_targets(settings, region_pin=pin, default_model=model)
    except RegionUnavailable as exc:
        log_gateway_event("extractions_region_unavailable", {"pin": exc.pin})
        return _error(400, "region_unavailable", str(exc))
    if not targets:
        log_gateway_event(
            "extractions_frontier_unavailable",
            {"reason": "frontier_disabled_or_no_key"},
        )
        return _error(501, "not_implemented", _UNAVAILABLE_FRONTIER)

    denied = reject_disallowed_model(request, model, settings)
    if denied is not None:
        return denied
    retired = reject_retired_model(request, model, settings)
    if retired is not None:
        return retired
    user_denied = reject_end_user(request, settings, body.user)
    if user_denied is not None:
        return user_denied

    started = time.perf_counter()
    payload = _request_payload(model, body)
    retry_settings = getattr(getattr(settings, "upstream", None), "retry", None)
    last_exc: Exception | None = None
    last_upstream: httpx.Response | None = None
    metrics = getattr(ctx, "metrics", None)

    for target in targets:
        headers = {
            "Authorization": f"Bearer {target.api_key}",
            "Content-Type": "application/json",
        }
        url = _frontier_extractions_url(target.base_url)
        try:
            upstream = await post_l6(
                _shared_client(),
                url,
                headers=headers,
                payload=payload,
                timeout=target.timeout,
                upstream="extractions",
                retry=target.retry if target.retry is not None else retry_settings,
                metrics=metrics,
            )
        except httpx.HTTPStatusError as exc:
            last_upstream = exc.response
            last_exc = exc
            log_gateway_event(
                "extractions_slot_error",
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
                "extractions_slot_error",
                {"slot": target.slot_id, "error": summarize_upstream_failure(exc)},
            )
            continue
        if is_slot_failure(upstream):
            last_upstream = upstream
            log_gateway_event(
                "extractions_slot_http",
                {"slot": target.slot_id, "status": upstream.status_code},
            )
            continue
        if upstream.status_code >= 400:
            log_gateway_event(
                "extractions_upstream_http",
                {"status": upstream.status_code, "slot": target.slot_id},
            )
            try:
                detail = upstream.json()
            except Exception:
                detail = {
                    "error": {
                        "type": "upstream_error",
                        "message": (upstream.text or "")[:200],
                    }
                }
            return JSONResponse(status_code=upstream.status_code, content=detail)

        try:
            data = upstream.json()
        except Exception:
            return _error(502, "bad_gateway", "Extractions upstream returned non-JSON.")
        if not isinstance(data, dict):
            return _error(502, "bad_gateway", "Extractions upstream returned non-object JSON.")

        latency_ms = _elapsed_ms(started)
        usage = data.get("usage") if isinstance(data.get("usage"), dict) else {}
        try:
            input_tokens = int(usage.get("input_tokens") or usage.get("prompt_tokens") or 0)
        except (TypeError, ValueError):
            input_tokens = 0
        try:
            output_tokens = int(usage.get("output_tokens") or usage.get("completion_tokens") or 0)
        except (TypeError, ValueError):
            output_tokens = 0
        prompt_chars = _prompt_chars(body)
        if input_tokens <= 0:
            input_tokens = max(0, prompt_chars // 4)

        resolved_model = str(data.get("model") or model)
        pricing = getattr(getattr(ctx, "router", None), "pricing", None) or getattr(
            settings, "pricing", None
        )
        usage_settings = getattr(settings, "usage", None)
        fallback = float(getattr(usage_settings, "frontier_price_per_1k_tokens", 0.002) or 0.002)
        from daari.gateway.provider_prefs import usage_cost_and_cache

        reported, cached_tokens, cache_write_tokens = usage_cost_and_cache(data)
        if reported is not None:
            spent = float(reported)
        else:
            spent = cost_usd(
                resolved_model,
                input_tokens,
                max(0, output_tokens),
                pricing,
                fallback_per_1k=fallback,
                cached_input_tokens=int(cached_tokens or 0),
                cache_write_tokens=int(cache_write_tokens or 0),
                billing_path="extractions",
                region_pin=region_pin_from_request(request),
            )
        caller = _caller_client_id(request)
        _bind_spend_context(
            request, ctx, model=resolved_model, client_id=caller, user_id=body.user
        )
        _record_request(
            ctx,
            client_id=caller,
            model=resolved_model,
            prompt_chars=prompt_chars,
            input_tokens=input_tokens,
            output_tokens=max(0, output_tokens),
            latency_ms=latency_ms,
            provider="frontier",
            cost_usd_value=spent,
            user_id=body.user,
            tier="extractions",
        )

        out = dict(data)
        out["daari_meta"] = {
            "tier": "extractions",
            "executor": "frontier",
            "provider_id": target.slot_id or "frontier",
            "model": resolved_model,
            "latency_ms": latency_ms,
            "input_tokens": input_tokens,
            "output_tokens": max(0, output_tokens),
            "usage_estimated": not bool(
                usage.get("input_tokens") or usage.get("prompt_tokens")
            ),
            "cache_hit": False,
            "cost_usd": spent,
        }
        log_gateway_event(
            "extractions_frontier_ok",
            {"model": resolved_model, "slot": target.slot_id, "latency_ms": latency_ms},
        )
        from daari.gateway.cost_headers import modality_response_headers, session_id_from_request

        cost_headers = modality_response_headers(
            settings,
            tier="extractions",
            model=resolved_model,
            prompt_chars=prompt_chars,
            input_tokens=input_tokens,
            output_tokens=max(0, output_tokens),
            cost_usd=spent,
            executor="frontier",
            session_id=session_id_from_request(request),
            savings=getattr(getattr(ctx, "router", None), "session_savings", None),
        )
        return JSONResponse(out, headers=cost_headers)

    if last_upstream is not None:
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
            "extractions_upstream_error",
            {"error": summarize_upstream_failure(last_exc)},
        )
    return _error(503, "upstream_error", "Extractions upstream request failed.")


async def _dispatch_extractions(request: Request, body: ExtractionsRequest) -> Any:
    ctx = request.app.state.ctx
    settings = ctx.settings
    requested = (body.model or "").strip()

    if requested:
        from daari.gateway.model_access import reject_retired_model

        retired = reject_retired_model(request, requested, settings)
        if retired is not None:
            return retired

    if not requested:
        return await _handle_local(request, body, model=default_local_model(settings))

    canonical = normalize_extractions_model(requested, settings=settings)
    if canonical is None:
        local = ", ".join(sorted(local_decisions_models(settings) | BUILTIN_LOCAL_MODELS))
        frontier = ", ".join(sorted(_FRONTIER_EXTRACTION_MODELS))
        return _error(
            400,
            "invalid_request",
            f"Unknown extractions model '{requested}'. "
            f"Use a local decision/extraction model ({local}) "
            f"or a frontier extraction slug ({frontier}).",
        )
    if is_frontier_extractions_model(canonical):
        return await _handle_frontier(request, body, model=canonical)
    return await _handle_local(request, body, model=canonical)


async def handle_extractions(request: Request, body: ExtractionsRequest) -> Any:
    """POST /v1/extractions."""
    return await _dispatch_extractions(request, body)
