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


def explicit_systemone_base(settings: Any) -> str:
    """Configured ``systemone.base_url``, or empty when the Ollama fallback applies."""
    systemone = getattr(settings, "systemone", None)
    return str(getattr(systemone, "base_url", "") or "").strip().rstrip("/")


def resolve_systemone_base(settings: Any, *, fallback: str = "") -> str:
    """Upstream root: explicit ``systemone.base_url``, else ``fallback``, else Ollama."""
    explicit = explicit_systemone_base(settings)
    if explicit:
        return explicit
    hinted = (fallback or "").strip().rstrip("/")
    if hinted:
        return hinted
    ollama = getattr(settings, "ollama", None)
    return str(getattr(ollama, "base_url", "") or "").strip().rstrip("/")


def resolve_systemone_api_key(settings: Any = None) -> str | None:
    """Resolved ``systemone.api_key`` (``secret://`` via ``current_secret``), or None."""
    if settings is None:
        return None
    systemone = getattr(settings, "systemone", None)
    raw = getattr(systemone, "api_key", None) if systemone is not None else None
    if raw is None:
        return None
    from daari.security.secret_refs import current_secret, register_secret

    value = current_secret(raw) if isinstance(raw, str) else None
    text = str(value or "").strip()
    if not text:
        return None
    register_secret(text)
    return text


def systemone_auth_headers(settings: Any = None, *, api_key: str | None = None) -> dict[str, str]:
    """Authorization Bearer when an api key is configured; empty dict otherwise."""
    key = (api_key or "").strip() if api_key is not None else None
    if key is None:
        key = resolve_systemone_api_key(settings) or ""
    if not key:
        return {}
    return {"Authorization": f"Bearer {key}"}


def _bad_upstream_body(explicit: str, base: str, *, kind: str) -> str:
    """502 text for a body that is not a JSON object.

    An explicit ``systemone.base_url`` names that host. The Ollama fallback
    keeps the existing wording.
    """
    if explicit:
        host = httpx.URL(base).host or base
        return f"systemone upstream at {host} returned {kind}."
    if kind == "non-JSON":
        return "Ollama systemone returned non-JSON."
    return "Ollama systemone returned non-object JSON."


def systemone_override_unavailable(base: str) -> str:
    root = (base or "").strip().rstrip("/")
    return (
        "Decision models could not reach the configured systemone upstream "
        f"at {root}. Start that server or update systemone.base_url."
    )


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


def _systemone_input_text(body: SystemOneRequest) -> str:
    """Flatten state + questions for input guardrail screening (#1476)."""
    parts: list[str] = []
    if isinstance(body.state, str):
        parts.append(body.state)
    else:
        try:
            parts.append(json.dumps(body.state, default=str))
        except Exception:
            parts.append(str(body.state))
    try:
        parts.append(json.dumps(body.questions, default=str))
    except Exception:
        parts.append(str(body.questions))
    return "\n".join(parts)


def _apply_systemone_output_policy(
    data: dict[str, Any],
    engine: Any,
    *,
    metrics: Any = None,
) -> tuple[dict[str, Any] | None, Any]:
    """Screen judgment text (answers) through output guardrails (#1476)."""
    from daari.gateway.guardrails import (
        apply_endpoint_output_policy,
        endpoint_guardrail_blocked_response,
    )

    answers = data.get("answers")
    if not isinstance(answers, dict):
        return data, None
    rewritten: dict[str, Any] = {}
    for key, value in answers.items():
        if isinstance(value, dict):
            choice = str(value.get("choice") or "")
            if choice:
                policy = apply_endpoint_output_policy(choice, engine, metrics=metrics)
                if policy.blocked:
                    return None, endpoint_guardrail_blocked_response(policy.block_message)
                rewritten[key] = {**value, "choice": policy.text}
            else:
                rewritten[key] = value
        elif isinstance(value, str):
            policy = apply_endpoint_output_policy(value, engine, metrics=metrics)
            if policy.blocked:
                return None, endpoint_guardrail_blocked_response(policy.block_message)
            rewritten[key] = policy.text
        else:
            rewritten[key] = value
    return {**data, "answers": rewritten}, None


async def _post_systemone(
    url: str,
    *,
    payload: dict[str, Any],
    timeout: float,
    retry: Any | None = None,
    metrics: Any | None = None,
    headers: dict[str, str] | None = None,
    settings: Any | None = None,
) -> httpx.Response:
    from daari.router.retry import RETRYABLE_STATUS, RetryPolicy, run_upstream

    policy = (
        retry
        if isinstance(retry, RetryPolicy)
        else (RetryPolicy(attempts=1) if retry is None else RetryPolicy.from_settings(retry))
    )
    auth = dict(headers) if headers else systemone_auth_headers(settings)

    async def attempt() -> httpx.Response:
        response = await _shared_client().post(
            url, json=payload, timeout=timeout, headers=auth or None
        )
        if response.status_code in RETRYABLE_STATUS:
            response.raise_for_status()
        return response

    return await run_upstream(
        attempt,
        upstream="systemone",
        policy=policy,
        timeout=timeout,
        metrics=metrics,
    )


async def _dispatch_systemone(request: Request, body: SystemOneRequest) -> Any:
    ctx = request.app.state.ctx
    settings = ctx.settings
    systemone = getattr(settings, "systemone", None)
    if systemone is not None and not bool(getattr(systemone, "enabled", True)):
        log_gateway_event("systemone_disabled", {})
        return _error(501, "not_implemented", _DISABLED)

    explicit = explicit_systemone_base(settings)
    base = resolve_systemone_base(settings)
    if not base:
        log_gateway_event("systemone_unavailable", {"reason": "no_ollama_base_url"})
        return _error(503, "backend_unavailable", _UNAVAILABLE)

    model = (body.model or "").strip()
    if not model:
        return _error(400, "invalid_request", "model: Field required")

    from daari.gateway.model_access import reject_disallowed_model, reject_retired_model

    denied = reject_disallowed_model(request, model, settings)
    if denied is not None:
        return denied
    retired = reject_retired_model(request, model, settings)
    if retired is not None:
        return retired

    metrics = getattr(ctx, "metrics", None)
    from daari.gateway.guardrails import (
        apply_endpoint_input_policy,
        endpoint_guardrail_blocked_response,
        router_guardrails,
    )

    engine = router_guardrails(ctx)
    input_policy = apply_endpoint_input_policy(
        _systemone_input_text(body), engine, metrics=metrics
    )
    if input_policy.blocked:
        return endpoint_guardrail_blocked_response(input_policy.block_message)

    state = body.state
    if isinstance(body.state, str):
        state_policy = apply_endpoint_input_policy(body.state, engine, metrics=metrics)
        if state_policy.blocked:
            return endpoint_guardrail_blocked_response(state_policy.block_message)
        state = state_policy.text

    payload = {
        "model": model,
        "state": state,
        "questions": body.questions,
    }
    if body.images is not None:
        payload["images"] = list(body.images)
    timeout = float(
        getattr(getattr(settings, "upstream", None), "local_timeout_seconds", 120.0) or 120.0
    )
    retry_settings = getattr(getattr(settings, "upstream", None), "retry", None)
    url = f"{base}/v1/systemone"
    from daari.observability.metrics import genai_operation_name
    from daari.observability.otel import modality_client_span

    span_attrs = {
        "daari.modality": "systemone",
        "gen_ai.operation.name": genai_operation_name("systemone"),
        "gen_ai.request.model": model,
    }
    started = time.perf_counter()
    try:
        with modality_client_span("daari.systemone", attributes=span_attrs):
            upstream = await _post_systemone(
                url,
                payload=payload,
                timeout=timeout,
                retry=retry_settings,
                metrics=metrics,
                settings=settings,
            )
    except httpx.RequestError as exc:
        log_gateway_event(
            "systemone_ollama_down",
            {"error": summarize_upstream_failure(exc), "url_host": httpx.URL(url).host},
        )
        if explicit:
            message = systemone_override_unavailable(explicit)
        else:
            message = backend_unavailable_message(exc) or _UNAVAILABLE
        return _error(503, "backend_unavailable", message)

    latency_ms = _elapsed_ms(started)
    if upstream.status_code >= 400:
        from daari.router.retry import provider_request_id

        http_payload: dict[str, Any] = {"status": upstream.status_code}
        request_id = provider_request_id(getattr(upstream, "headers", None))
        if request_id:
            http_payload["upstream_request_id"] = request_id
        log_gateway_event("systemone_upstream_http", http_payload)
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

    upstream_kind = "openai-compat" if explicit else "ollama"
    try:
        data = upstream.json()
    except Exception:
        return _error(502, "bad_gateway", _bad_upstream_body(explicit, base, kind="non-JSON"))
    if not isinstance(data, dict):
        return _error(
            502, "bad_gateway", _bad_upstream_body(explicit, base, kind="non-object JSON")
        )

    data, blocked = _apply_systemone_output_policy(data, engine, metrics=metrics)
    if blocked is not None:
        return blocked
    assert data is not None

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
        "executor": upstream_kind,
        "provider_id": upstream_kind,
        "model": str(data.get("model") or model),
        "latency_ms": latency_ms,
        "input_tokens": input_tokens,
        "output_tokens": max(0, output_tokens),
        "usage_estimated": not bool(usage.get("input_tokens")),
        "cache_hit": False,
    }
    log_gateway_event(
        "systemone_ok",
        {
            "model": model,
            "latency_ms": latency_ms,
            "input_tokens": input_tokens,
            "upstream": upstream_kind,
        },
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


async def handle_systemone(request: Request, body: SystemOneRequest) -> Any:
    """POST /v1/systemone with Idempotency-Key replay (#1618)."""
    from daari.gateway.idempotency import (
        abandon_slot,
        complete_json_slot,
        resolve_idempotency,
    )

    ctx = request.app.state.ctx
    idem_kind, idem_response, idem_slot = await resolve_idempotency(request, ctx, body)
    if idem_kind in {"replay", "conflict"} and idem_response is not None:
        return idem_response

    try:
        response = await _dispatch_systemone(request, body)
    except Exception:
        abandon_slot(idem_slot)
        raise

    if isinstance(response, JSONResponse) and 200 <= response.status_code < 300:
        try:
            payload = json.loads(response.body)
        except Exception:
            abandon_slot(idem_slot)
            return response
        if isinstance(payload, dict):
            complete_json_slot(
                idem_slot, status_code=response.status_code, payload=payload
            )
        else:
            abandon_slot(idem_slot)
        return response

    abandon_slot(idem_slot)
    return response
