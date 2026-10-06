"""POST /v1/systemone — Ollama decision-model facade (#1291)."""

from __future__ import annotations

import json
import time
from typing import Any

import httpx
from fastapi import Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from daari.gateway.client_errors import backend_unavailable_message, summarize_upstream_failure
from daari.gateway.request_log import log_gateway_event

_UNAVAILABLE = (
    "Decision models require Ollama with /v1/systemone (0.35+). "
    "Start Ollama or set ollama.base_url; set systemone.enabled=false to disable."
)

_DISABLED = (
    "POST /v1/systemone is disabled (systemone.enabled=false). "
    "Enable it to proxy decision models to Ollama."
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


class SystemOneRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    model: str
    state: Any
    questions: dict[str, Any] = Field(min_length=1)
    # Ollama 0.35.1+ Clef multimodal: base64 image strings scored with state.
    images: list[str] | None = None


def _error(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"error": {"type": code, "message": message}},
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
            user_id="",
            request_id=str(getattr(request.state, "request_id", None) or ""),
            requested_model=model,
            pricing=pricing,
            fallback_per_1k=fallback,
            reported_cost=0.0,
        )
    )


def _prompt_chars(body: SystemOneRequest) -> int:
    try:
        return len(json.dumps({"state": body.state, "questions": body.questions}, default=str))
    except Exception:
        return len(str(body.state)) + len(str(body.questions))


def _elapsed_ms(started: float) -> int:
    elapsed = time.perf_counter() - started
    millis = int(elapsed * 1000)
    if millis <= 0 and elapsed > 0:
        return 1
    return max(0, millis)


def _record_request(
    ctx: Any,
    *,
    client_id: str | None,
    model: str,
    prompt_chars: int,
    input_tokens: int,
    output_tokens: int,
    latency_ms: int,
) -> None:
    metrics = getattr(ctx, "metrics", None)
    if metrics is not None:
        metrics.record(
            "systemone",
            cache_hit=False,
            modality="systemone",
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=latency_ms,
        )
    ledger = getattr(getattr(ctx, "router", None), "usage_ledger", None)
    if ledger is None:
        return
    ledger.record(
        tier="systemone",
        cache_hit=False,
        prompt_chars=prompt_chars,
        completion_chars=0,
        client_id=client_id,
        model=model,
        provider="ollama",
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        reported_cost=0.0,
    )


def parse_systemone_body(raw: Any) -> SystemOneRequest | JSONResponse:
    """Validate Ollama-shaped body; malformed → 400."""
    if not isinstance(raw, dict):
        return _error(400, "invalid_request", "Request body must be a JSON object.")
    try:
        return SystemOneRequest.model_validate(raw)
    except ValidationError as exc:
        first = exc.errors()[0] if exc.errors() else {}
        loc = ".".join(str(part) for part in first.get("loc", ()) ) or "body"
        msg = first.get("msg") or "invalid request"
        return _error(400, "invalid_request", f"{loc}: {msg}")


async def handle_systemone(request: Request, body: SystemOneRequest) -> Any:
    ctx = request.app.state.ctx
    settings = ctx.settings
    systemone = getattr(settings, "systemone", None)
    if systemone is not None and not bool(getattr(systemone, "enabled", True)):
        log_gateway_event("systemone_disabled", {})
        return _error(501, "not_implemented", _DISABLED)

    ollama = getattr(settings, "ollama", None)
    base = str(getattr(ollama, "base_url", "") or "").strip().rstrip("/")
    if not base:
        log_gateway_event("systemone_unavailable", {"reason": "no_ollama_base_url"})
        return _error(503, "backend_unavailable", _UNAVAILABLE)

    model = (body.model or "").strip()
    if not model:
        return _error(400, "invalid_request", "model: Field required")

    from daari.gateway.model_access import reject_disallowed_model

    denied = reject_disallowed_model(request, model, settings)
    if denied is not None:
        return denied

    payload = {
        "model": model,
        "state": body.state,
        "questions": body.questions,
    }
    if body.images is not None:
        payload["images"] = list(body.images)
    timeout = float(
        getattr(getattr(settings, "upstream", None), "local_timeout_seconds", 120.0) or 120.0
    )
    url = f"{base}/v1/systemone"
    started = time.perf_counter()
    try:
        upstream = await _shared_client().post(url, json=payload, timeout=timeout)
    except httpx.RequestError as exc:
        log_gateway_event(
            "systemone_ollama_down",
            {"error": summarize_upstream_failure(exc), "url_host": httpx.URL(url).host},
        )
        return _error(503, "backend_unavailable", backend_unavailable_message(exc) or _UNAVAILABLE)

    latency_ms = _elapsed_ms(started)
    if upstream.status_code >= 400:
        log_gateway_event(
            "systemone_upstream_http",
            {"status": upstream.status_code},
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
        return _error(502, "bad_gateway", "Ollama systemone returned non-JSON.")
    if not isinstance(data, dict):
        return _error(502, "bad_gateway", "Ollama systemone returned non-object JSON.")

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

    caller = _caller_client_id(request)
    _bind_spend_context(request, ctx, model=model, client_id=caller)
    _record_request(
        ctx,
        client_id=caller,
        model=str(data.get("model") or model),
        prompt_chars=prompt_chars,
        input_tokens=input_tokens,
        output_tokens=max(0, output_tokens),
        latency_ms=latency_ms,
    )

    data = dict(data)
    data["daari_meta"] = {
        "tier": "systemone",
        "executor": "ollama",
        "provider_id": "ollama",
        "model": str(data.get("model") or model),
        "latency_ms": latency_ms,
        "input_tokens": input_tokens,
        "output_tokens": max(0, output_tokens),
        "usage_estimated": not bool(usage.get("input_tokens")),
        "cache_hit": False,
    }
    log_gateway_event(
        "systemone_ok",
        {"model": model, "latency_ms": latency_ms, "input_tokens": input_tokens},
    )
    from daari.gateway.cost_headers import modality_response_headers, session_id_from_request

    headers = modality_response_headers(
        settings,
        tier="systemone",
        model=str(data.get("model") or model),
        prompt_chars=prompt_chars,
        input_tokens=input_tokens,
        output_tokens=max(0, output_tokens),
        cost_usd=0.0,
        session_id=session_id_from_request(request),
        savings=getattr(getattr(ctx, "router", None), "session_savings", None),
    )
    return JSONResponse(data, headers=headers)
