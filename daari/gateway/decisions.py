"""POST /v1/decisions — OpenAI Decisions beta on local models + gpt-6-luna (#1474)."""

from __future__ import annotations

import json
import re
import time
from typing import Any

import httpx
from fastapi import Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from daari.gateway.client_errors import backend_unavailable_message, summarize_upstream_failure
from daari.gateway.l6_passthrough import (
    RegionUnavailable,
    is_slot_failure,
    post_l6,
    region_pin_from_request,
    resolve_l6_targets,
)
from daari.gateway.request_log import log_gateway_event
from daari.pricing import cost_usd, matching_model_key

_LOCAL_MODELS = frozenset({"clef", "clef-flash", "nimble", "tev1"})
_FRONTIER_DECISIONS_KEYS = ("gpt-6-luna",)

_DATA_URI_RE = re.compile(
    r"^data:(?P<mime>[^;]+);base64,(?P<data>.+)$", re.IGNORECASE | re.DOTALL
)

_UNAVAILABLE_LOCAL = (
    "Local decisions require Ollama with /v1/systemone (0.35+) and "
    "systemone.enabled=true. Start Ollama or set ollama.base_url."
)

_UNAVAILABLE_FRONTIER = (
    "Decisions for gpt-6-luna require a configured frontier (L6) "
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


class DecisionChoiceOption(BaseModel):
    model_config = ConfigDict(extra="ignore")

    value: str | int | float | bool
    description: str | None = None


class DecisionLevel(BaseModel):
    model_config = ConfigDict(extra="ignore")

    label: str
    description: str | None = None


class DecisionQuestion(BaseModel):
    model_config = ConfigDict(extra="ignore")

    type: str
    name: str | None = None
    instructions: str
    choices: list[DecisionChoiceOption] | None = None
    levels: list[DecisionLevel] | None = None


class DecisionsRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    model: str | None = None
    input: Any
    questions: list[DecisionQuestion] = Field(min_length=1)
    user: str | None = None


def _error(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"error": {"type": code, "message": message}},
    )


def parse_decisions_body(raw: Any) -> DecisionsRequest | JSONResponse:
    if not isinstance(raw, dict):
        return _error(400, "invalid_request", "Request body must be a JSON object.")
    try:
        return DecisionsRequest.model_validate(raw)
    except ValidationError as exc:
        first = exc.errors()[0] if exc.errors() else {}
        loc = ".".join(str(part) for part in first.get("loc", ())) or "body"
        msg = first.get("msg") or "invalid request"
        return _error(400, "invalid_request", f"{loc}: {msg}")


def is_frontier_decisions_model(model: str) -> bool:
    name = (model or "").strip()
    if not name:
        return False
    key = matching_model_key(name, {k: True for k in _FRONTIER_DECISIONS_KEYS})
    return key is not None


def is_local_decisions_model(model: str) -> bool:
    name = (model or "").strip().lower()
    if not name:
        return False
    # Strip vendor / dated suffixes for local catalog ids.
    base = name.split("/", 1)[-1]
    if "." in base:
        base = base.rsplit(".", 1)[-1]
    for local in _LOCAL_MODELS:
        if base == local or base.startswith(f"{local}-") or base.startswith(f"{local}:"):
            return True
    return name in _LOCAL_MODELS


def default_local_model(settings: Any) -> str:
    routing = getattr(settings, "routing", None)
    classifier = getattr(routing, "decision_classifier", None) if routing is not None else None
    model = str(getattr(classifier, "model", "") or "").strip() if classifier else ""
    return model or "nimble"


def _caller_client_id(request: Request) -> str | None:
    claims = getattr(request.state, "auth_claims", None)
    if claims is None or getattr(claims, "kind", None) != "virtual":
        return None
    client_id = getattr(claims, "client_id", None) or getattr(claims, "key_id", None)
    text = str(client_id or "").strip()
    return text or None


def _elapsed_ms(started: float) -> int:
    elapsed = time.perf_counter() - started
    millis = int(elapsed * 1000)
    if millis <= 0 and elapsed > 0:
        return 1
    return max(0, millis)


def _extract_input_text_and_images(value: Any) -> tuple[str, list[str]]:
    """OpenAI Decisions input → (state text, base64 images)."""
    if isinstance(value, str):
        return value, []
    texts: list[str] = []
    images: list[str] = []
    if not isinstance(value, list):
        return str(value), []
    for item in value:
        if isinstance(item, str):
            texts.append(item)
            continue
        if not isinstance(item, dict):
            continue
        content = item.get("content", item)
        if isinstance(content, str):
            texts.append(content)
            continue
        if not isinstance(content, list):
            continue
        for part in content:
            if not isinstance(part, dict):
                continue
            ptype = str(part.get("type") or "")
            if ptype in {"input_text", "text"}:
                text = part.get("text")
                if text is not None:
                    texts.append(str(text))
            elif ptype in {"input_image", "image_url"}:
                url = part.get("image_url")
                if isinstance(url, dict):
                    url = url.get("url")
                raw = str(url or "").strip()
                if not raw:
                    continue
                match = _DATA_URI_RE.match(raw)
                if match:
                    images.append(match.group("data"))
                elif "," in raw and "base64" in raw.lower():
                    images.append(raw.split(",", 1)[1])
                else:
                    # Plain base64 blob without data URI prefix.
                    images.append(raw)
    return "\n".join(texts).strip(), images


def _openai_questions_to_systemone(questions: list[DecisionQuestion]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for index, question in enumerate(questions):
        name = (question.name or f"q{index}").strip() or f"q{index}"
        qtype = (question.type or "").strip().lower()
        entry: dict[str, Any] = {"instructions": question.instructions}
        if qtype == "predicate":
            entry["type"] = "boolean"
        elif qtype == "choice":
            entry["type"] = "choice"
            criteria: dict[str, str] = {}
            for option in question.choices or []:
                key = str(option.value)
                criteria[key] = str(option.description or key)
            entry["criteria"] = criteria
        elif qtype == "score":
            entry["type"] = "score"
            criteria = {}
            for level in question.levels or []:
                criteria[level.label] = str(level.description or level.label)
            entry["criteria"] = criteria
        else:
            entry["type"] = qtype or "boolean"
        out[name] = entry
    return out


def _systemone_answers_to_openai(answers: Any) -> list[dict[str, Any]]:
    if isinstance(answers, list):
        return [item for item in answers if isinstance(item, dict)]
    if not isinstance(answers, dict):
        return []
    converted: list[dict[str, Any]] = []
    for name, raw in answers.items():
        if not isinstance(raw, dict):
            continue
        item = dict(raw)
        item.setdefault("name", name)
        qtype = str(item.get("type") or "").lower()
        if qtype == "boolean":
            item["type"] = "predicate"
            if "probability" not in item and "confidence" in item:
                item["probability"] = item.get("confidence")
        probs = item.get("probabilities")
        if isinstance(probs, dict):
            item["probabilities"] = [
                {"value": key, "probability": float(val)} for key, val in probs.items()
            ]
        converted.append(item)
    return converted


def _decisions_input_text(body: DecisionsRequest) -> str:
    """Flatten input + questions for input guardrail screening (#1497)."""
    parts: list[str] = []
    state, _images = _extract_input_text_and_images(body.input)
    if state:
        parts.append(state)
    else:
        try:
            parts.append(json.dumps(body.input, default=str))
        except Exception:
            parts.append(str(body.input))
    try:
        parts.append(
            json.dumps([q.model_dump(exclude_none=True) for q in body.questions], default=str)
        )
    except Exception:
        parts.append(str(body.questions))
    return "\n".join(parts)


def _apply_decisions_input_policy(
    body: DecisionsRequest,
    engine: Any,
    *,
    metrics: Any = None,
) -> tuple[DecisionsRequest | None, Any]:
    """Screen flattened input + questions; rewrite string input (systemone parity)."""
    from daari.gateway.guardrails import (
        apply_endpoint_input_policy,
        endpoint_guardrail_blocked_response,
    )

    input_policy = apply_endpoint_input_policy(
        _decisions_input_text(body), engine, metrics=metrics
    )
    if input_policy.blocked:
        return None, endpoint_guardrail_blocked_response(input_policy.block_message)

    if isinstance(body.input, str):
        state_policy = apply_endpoint_input_policy(body.input, engine, metrics=metrics)
        if state_policy.blocked:
            return None, endpoint_guardrail_blocked_response(state_policy.block_message)
        if state_policy.text != body.input:
            body = body.model_copy(update={"input": state_policy.text})
    return body, None


def _apply_decisions_output_policy(
    data: dict[str, Any],
    engine: Any,
    *,
    metrics: Any = None,
) -> tuple[dict[str, Any] | None, Any]:
    """Screen answer text through output guardrails (#1497)."""
    from daari.gateway.guardrails import (
        apply_endpoint_output_policy,
        endpoint_guardrail_blocked_response,
    )
    from daari.gateway.systemone import _apply_systemone_output_policy

    answers = data.get("answers")
    if isinstance(answers, dict):
        return _apply_systemone_output_policy(data, engine, metrics=metrics)
    if not isinstance(answers, list):
        return data, None
    rewritten: list[Any] = []
    for item in answers:
        if isinstance(item, dict):
            choice = str(item.get("choice") or "")
            if choice:
                policy = apply_endpoint_output_policy(choice, engine, metrics=metrics)
                if policy.blocked:
                    return None, endpoint_guardrail_blocked_response(policy.block_message)
                rewritten.append({**item, "choice": policy.text})
            else:
                rewritten.append(item)
        elif isinstance(item, str):
            policy = apply_endpoint_output_policy(item, engine, metrics=metrics)
            if policy.blocked:
                return None, endpoint_guardrail_blocked_response(policy.block_message)
            rewritten.append(policy.text)
        else:
            rewritten.append(item)
    return {**data, "answers": rewritten}, None


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
) -> None:
    metrics = getattr(ctx, "metrics", None)
    if metrics is not None:
        metrics.record(
            "decisions",
            cache_hit=False,
            modality="decisions",
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=latency_ms,
        )
    ledger = getattr(getattr(ctx, "router", None), "usage_ledger", None)
    if ledger is None:
        return
    ledger.record(
        tier="decisions",
        cache_hit=False,
        prompt_chars=prompt_chars,
        completion_chars=0,
        client_id=client_id,
        model=model,
        provider=provider,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        reported_cost=cost_usd_value,
    )


def _prompt_chars(state: str, questions: list[DecisionQuestion]) -> int:
    try:
        return len(
            json.dumps(
                {
                    "state": state,
                    "questions": [q.model_dump(exclude_none=True) for q in questions],
                },
                default=str,
            )
        )
    except Exception:
        return len(state) + sum(len(q.instructions) for q in questions)


async def _handle_local(
    request: Request,
    body: DecisionsRequest,
    *,
    model: str,
) -> Any:
    ctx = request.app.state.ctx
    settings = ctx.settings
    systemone = getattr(settings, "systemone", None)
    if systemone is not None and not bool(getattr(systemone, "enabled", True)):
        log_gateway_event("decisions_local_disabled", {})
        return _error(501, "not_implemented", _UNAVAILABLE_LOCAL)

    ollama = getattr(settings, "ollama", None)
    base = str(getattr(ollama, "base_url", "") or "").strip().rstrip("/")
    if not base:
        log_gateway_event("decisions_local_unavailable", {"reason": "no_ollama_base_url"})
        return _error(503, "backend_unavailable", _UNAVAILABLE_LOCAL)

    from daari.gateway.model_access import reject_disallowed_model

    denied = reject_disallowed_model(request, model, settings)
    if denied is not None:
        return denied

    metrics = getattr(ctx, "metrics", None)
    from daari.gateway.guardrails import router_guardrails

    engine = router_guardrails(ctx)
    body, blocked = _apply_decisions_input_policy(body, engine, metrics=metrics)
    if blocked is not None:
        return blocked
    assert body is not None

    state, images = _extract_input_text_and_images(body.input)
    payload: dict[str, Any] = {
        "model": model,
        "state": state,
        "questions": _openai_questions_to_systemone(body.questions),
    }
    if images:
        payload["images"] = images

    # Reuse systemone retry helper so local decisions share pool + retry (#1497).
    from daari.gateway import systemone as systemone_mod
    from daari.observability.metrics import genai_operation_name
    from daari.observability.otel import modality_client_span

    timeout = float(
        getattr(getattr(settings, "upstream", None), "local_timeout_seconds", 120.0) or 120.0
    )
    retry_settings = getattr(getattr(settings, "upstream", None), "retry", None)
    url = f"{base}/v1/systemone"
    span_attrs = {
        "daari.modality": "decisions",
        "gen_ai.operation.name": genai_operation_name("decisions"),
        "gen_ai.request.model": model,
    }
    started = time.perf_counter()
    try:
        with modality_client_span("daari.decisions", attributes=span_attrs):
            upstream = await systemone_mod._post_systemone(
                url,
                payload=payload,
                timeout=timeout,
                retry=retry_settings,
                metrics=metrics,
            )
    except httpx.RequestError as exc:
        log_gateway_event(
            "decisions_ollama_down",
            {"error": summarize_upstream_failure(exc), "url_host": httpx.URL(url).host},
        )
        return _error(
            503,
            "backend_unavailable",
            backend_unavailable_message(exc) or _UNAVAILABLE_LOCAL,
        )

    latency_ms = _elapsed_ms(started)
    if upstream.status_code >= 400:
        log_gateway_event("decisions_local_upstream_http", {"status": upstream.status_code})
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

    data, out_blocked = _apply_decisions_output_policy(data, engine, metrics=metrics)
    if out_blocked is not None:
        return out_blocked
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
    prompt_chars = _prompt_chars(state, body.questions)
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
    )

    out = {
        "id": data.get("id") or f"dec_local_{resolved_model}",
        "object": "decision",
        "model": resolved_model,
        "answers": _systemone_answers_to_openai(data.get("answers")),
        "usage": {
            "input_tokens": input_tokens,
            "output_tokens": max(0, output_tokens),
        },
        "daari_meta": {
            "tier": "decisions",
            "executor": "ollama",
            "provider_id": "ollama",
            "model": resolved_model,
            "latency_ms": latency_ms,
            "input_tokens": input_tokens,
            "output_tokens": max(0, output_tokens),
            "usage_estimated": not bool(usage.get("input_tokens")),
            "cache_hit": False,
        },
    }
    log_gateway_event(
        "decisions_local_ok",
        {"model": resolved_model, "latency_ms": latency_ms, "input_tokens": input_tokens},
    )
    from daari.gateway.cost_headers import modality_response_headers, session_id_from_request

    headers = modality_response_headers(
        settings,
        tier="decisions",
        model=resolved_model,
        prompt_chars=prompt_chars,
        input_tokens=input_tokens,
        output_tokens=max(0, output_tokens),
        cost_usd=0.0,
        session_id=session_id_from_request(request),
        savings=getattr(getattr(ctx, "router", None), "session_savings", None),
    )
    return JSONResponse(out, headers=headers)


async def _handle_frontier(
    request: Request,
    body: DecisionsRequest,
    *,
    model: str,
) -> Any:
    from daari.gateway.model_access import reject_disallowed_model, reject_frontier_passthrough

    blocked = reject_frontier_passthrough(request)
    if blocked is not None:
        return blocked

    ctx = request.app.state.ctx
    settings = ctx.settings
    pin = region_pin_from_request(request)
    try:
        targets = resolve_l6_targets(settings, region_pin=pin, default_model="gpt-6-luna")
    except RegionUnavailable as exc:
        log_gateway_event("decisions_region_unavailable", {"pin": exc.pin})
        return _error(400, "region_unavailable", str(exc))
    if not targets:
        log_gateway_event("decisions_frontier_unavailable", {"reason": "frontier_disabled_or_no_key"})
        return _error(501, "not_implemented", _UNAVAILABLE_FRONTIER)

    denied = reject_disallowed_model(request, model, settings)
    if denied is not None:
        return denied

    metrics = getattr(ctx, "metrics", None)
    from daari.gateway.guardrails import router_guardrails
    from daari.observability.metrics import genai_operation_name
    from daari.observability.otel import modality_client_span

    engine = router_guardrails(ctx)
    body, blocked_in = _apply_decisions_input_policy(body, engine, metrics=metrics)
    if blocked_in is not None:
        return blocked_in
    assert body is not None

    payload = {
        "model": model,
        "input": body.input,
        "questions": [q.model_dump(exclude_none=True) for q in body.questions],
    }
    retry_settings = getattr(getattr(settings, "upstream", None), "retry", None)
    last_exc: Exception | None = None
    last_upstream: httpx.Response | None = None
    started = time.perf_counter()
    span_attrs = {
        "daari.modality": "decisions",
        "gen_ai.operation.name": genai_operation_name("decisions"),
        "gen_ai.request.model": model,
    }

    for target in targets:
        headers = {
            "Authorization": f"Bearer {target.api_key}",
            "Content-Type": "application/json",
        }
        url = f"{target.base_url.rstrip('/')}/decisions"
        try:
            with modality_client_span("daari.decisions", attributes=span_attrs):
                upstream = await post_l6(
                    _shared_client(),
                    url,
                    headers=headers,
                    payload=payload,
                    timeout=target.timeout,
                    upstream="decisions",
                    retry=target.retry if target.retry is not None else retry_settings,
                    metrics=metrics,
                )
        except httpx.HTTPStatusError as exc:
            last_upstream = exc.response
            last_exc = exc
            log_gateway_event(
                "decisions_slot_error",
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
                "decisions_slot_error",
                {"slot": target.slot_id, "error": summarize_upstream_failure(exc)},
            )
            continue
        if is_slot_failure(upstream):
            last_upstream = upstream
            log_gateway_event(
                "decisions_slot_http",
                {"slot": target.slot_id, "status": upstream.status_code},
            )
            continue
        if upstream.status_code >= 400:
            log_gateway_event(
                "decisions_upstream_http",
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
            return _error(502, "bad_gateway", "Decisions upstream returned non-JSON.")
        if not isinstance(data, dict):
            return _error(502, "bad_gateway", "Decisions upstream returned non-object JSON.")

        data, out_blocked = _apply_decisions_output_policy(data, engine, metrics=metrics)
        if out_blocked is not None:
            return out_blocked
        assert data is not None

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
        state, _images = _extract_input_text_and_images(body.input)
        prompt_chars = _prompt_chars(state, body.questions)
        if input_tokens <= 0:
            input_tokens = max(0, prompt_chars // 4)

        resolved_model = str(data.get("model") or model)
        pricing = getattr(getattr(ctx, "router", None), "pricing", None) or getattr(
            settings, "pricing", None
        )
        usage_settings = getattr(settings, "usage", None)
        fallback = float(getattr(usage_settings, "frontier_price_per_1k_tokens", 0.002) or 0.002)
        from daari.gateway.provider_prefs import usage_cost_and_cache

        _reported, cached_tokens, cache_write_tokens = usage_cost_and_cache(data)
        spent = cost_usd(
            resolved_model,
            input_tokens,
            max(0, output_tokens),
            pricing,
            fallback_per_1k=fallback,
            cached_input_tokens=int(cached_tokens or 0),
            cache_write_tokens=int(cache_write_tokens or 0),
            billing_path="decisions",
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
        )

        out = dict(data)
        out["daari_meta"] = {
            "tier": "decisions",
            "executor": "frontier",
            "provider_id": target.slot_id or "frontier",
            "model": resolved_model,
            "latency_ms": latency_ms,
            "input_tokens": input_tokens,
            "output_tokens": max(0, output_tokens),
            "usage_estimated": not bool(usage.get("input_tokens") or usage.get("prompt_tokens")),
            "cache_hit": False,
            "cost_usd": spent,
        }
        log_gateway_event(
            "decisions_frontier_ok",
            {"model": resolved_model, "slot": target.slot_id, "latency_ms": latency_ms},
        )
        from daari.gateway.cost_headers import modality_response_headers, session_id_from_request

        cost_headers = modality_response_headers(
            settings,
            tier="decisions",
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
            "decisions_upstream_error",
            {"error": summarize_upstream_failure(last_exc)},
        )
    return _error(503, "upstream_error", "Decisions upstream request failed.")


async def handle_decisions(request: Request, body: DecisionsRequest) -> Any:
    ctx = request.app.state.ctx
    settings = ctx.settings
    requested = (body.model or "").strip()

    if is_frontier_decisions_model(requested):
        return await _handle_frontier(request, body, model=requested)

    if requested and not is_local_decisions_model(requested):
        # Unknown id: prefer frontier only when it looks like Luna Decisions;
        # otherwise treat as a local Ollama decision-model name.
        if "luna" in requested.lower() and "gpt-6" in requested.lower().replace(".", "-"):
            return await _handle_frontier(request, body, model=requested)

    model = requested or default_local_model(settings)
    if is_frontier_decisions_model(model):
        return await _handle_frontier(request, body, model=model)
    return await _handle_local(request, body, model=model)
