"""POST /v1/ocr — LiteLLM/Mistral-shaped OCR via local multimodal or L6 (#1263)."""

from __future__ import annotations

import base64
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

import httpx
from fastapi import Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from daari.gateway.client_errors import summarize_upstream_failure
from daari.gateway.l6_passthrough import (
    RegionUnavailable,
    is_slot_failure,
    post_l6,
    region_pin_from_request,
    resolve_l6_targets,
)
from daari.gateway.request_log import log_gateway_event

_UNAVAILABLE = (
    "OCR requires a configured local multimodal vision model "
    "(ocr.vision_model), a local OCR base_url (ocr.base_url), or a frontier "
    "(L6) OpenAI-compatible endpoint. Set one of those; daari does not invent "
    "document text locally without a backend."
)

_OCR_PROMPT = (
    "Extract all readable text from this image or document page as Markdown. "
    "Return only the extracted text with no preamble."
)

_DATA_URI_RE = re.compile(
    r"^data:(?P<mime>[^;]+);base64,(?P<data>.+)$", re.IGNORECASE | re.DOTALL
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
class OcrTarget:
    base_url: str
    api_key: str | None
    default_model: str
    via: str
    timeout: float
    slot_id: str = ""
    retry: Any | None = None


class OcrDocument(BaseModel):
    type: str | None = Field(default=None)
    document_url: str | None = Field(default=None)
    image_url: str | None = Field(default=None)


class OcrRequest(BaseModel):
    model: str | None = Field(default=None)
    document: OcrDocument | None = Field(default=None)
    pages: list[int] | None = Field(default=None)
    include_image_base64: bool | None = Field(default=None)
    image_limit: int | None = Field(default=None)
    image_min_size: int | None = Field(default=None)
    user: str | None = Field(default=None)


def _error(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"error": {"type": code, "message": message}},
    )


def resolve_ocr_targets(
    settings: Any, *, region_pin: str | None = None
) -> list[OcrTarget]:
    """Local OCR/base_url or vision model first; else L6 slots."""
    ocr = getattr(settings, "ocr", None)
    upstream = getattr(settings, "upstream", None)
    local_timeout = float(getattr(upstream, "local_timeout_seconds", 120.0) or 120.0)

    base = str(getattr(ocr, "base_url", "") or "").strip().rstrip("/") if ocr else ""
    model = str(getattr(ocr, "model", "") or "").strip() if ocr else ""
    if base:
        return [
            OcrTarget(
                base_url=base,
                api_key=None,
                default_model=model or "ocr",
                via="local",
                timeout=local_timeout,
            )
        ]

    vision = str(getattr(ocr, "vision_model", "") or "").strip() if ocr else ""
    if vision:
        ollama = getattr(settings, "ollama", None)
        ollama_base = str(getattr(ollama, "base_url", "") or "").strip().rstrip("/")
        if ollama_base:
            return [
                OcrTarget(
                    base_url=ollama_base,
                    api_key=None,
                    default_model=vision,
                    via="vision",
                    timeout=local_timeout,
                )
            ]

    l6 = resolve_l6_targets(
        settings, region_pin=region_pin, default_model=model or "mistral-ocr-latest"
    )
    return [
        OcrTarget(
            base_url=target.base_url,
            api_key=target.api_key,
            default_model=model or target.default_model,
            via="frontier",
            timeout=target.timeout,
            slot_id=target.slot_id,
            retry=target.retry,
        )
        for target in l6
    ]


def resolve_ocr_target(
    settings: Any, *, region_pin: str | None = None
) -> OcrTarget | None:
    try:
        targets = resolve_ocr_targets(settings, region_pin=region_pin)
    except RegionUnavailable:
        return None
    return targets[0] if targets else None


def _validate_document(document: OcrDocument | None) -> str | None:
    """Return an error message when the document body is invalid."""
    if document is None:
        return "document is required"
    doc_type = (document.type or "").strip().lower()
    if not doc_type:
        if document.image_url:
            doc_type = "image_url"
        elif document.document_url:
            doc_type = "document_url"
        else:
            return "document.type is required (document_url or image_url)"
    if doc_type == "image_url":
        if not (document.image_url or "").strip():
            return "document.image_url is required when type is image_url"
        return None
    if doc_type == "document_url":
        if not (document.document_url or "").strip():
            return "document.document_url is required when type is document_url"
        return None
    return "document.type must be document_url or image_url"


def _document_source(document: OcrDocument) -> tuple[str, str]:
    doc_type = (document.type or "").strip().lower()
    if not doc_type:
        doc_type = "image_url" if document.image_url else "document_url"
    if doc_type == "image_url":
        return "image_url", str(document.image_url or "").strip()
    return "document_url", str(document.document_url or "").strip()


def _image_b64_for_vision(source: str) -> str | None:
    """Extract raw base64 for Ollama /api/chat images from a data URI or reject URLs."""
    match = _DATA_URI_RE.match(source.strip())
    if match:
        return match.group("data").strip()
    # Ollama accepts raw base64 without a data URI prefix.
    if re.fullmatch(r"[A-Za-z0-9+/=\s]+", source) and len(source) > 32:
        return "".join(source.split())
    parsed = urlparse(source)
    if parsed.scheme in {"http", "https"}:
        return None  # fetch separately
    return None


async def _fetch_image_b64(url: str, timeout: float) -> str:
    client = _shared_client()
    response = await client.get(url, timeout=timeout)
    response.raise_for_status()
    return base64.b64encode(response.content).decode("ascii")


def _ocr_payload(body: OcrRequest, model: str) -> dict[str, Any]:
    assert body.document is not None
    doc_type, source = _document_source(body.document)
    document: dict[str, Any] = {"type": doc_type, doc_type: source}
    payload: dict[str, Any] = {"model": model, "document": document}
    if body.pages is not None:
        payload["pages"] = body.pages
    if body.include_image_base64 is not None:
        payload["include_image_base64"] = body.include_image_base64
    if body.image_limit is not None:
        payload["image_limit"] = body.image_limit
    if body.image_min_size is not None:
        payload["image_min_size"] = body.image_min_size
    return payload


def _vision_pages_response(*, model: str, markdown: str, source: str) -> dict[str, Any]:
    size = 0
    match = _DATA_URI_RE.match(source.strip())
    if match:
        try:
            size = len(base64.b64decode(match.group("data"), validate=False))
        except Exception:
            size = len(match.group("data"))
    else:
        size = len(source)
    return {
        "object": "ocr",
        "model": model,
        "pages": [
            {
                "index": 0,
                "markdown": markdown,
                "dimensions": None,
                "images": [],
            }
        ],
        "usage_info": {"pages_processed": 1, "doc_size_bytes": size},
        "document_annotation": None,
    }


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
    completion_chars: int,
) -> None:
    input_tokens = max(0, prompt_chars // 4)
    output_tokens = max(0, completion_chars // 4)
    metrics = getattr(ctx, "metrics", None)
    if metrics is not None:
        metrics.record(
            "ocr",
            cache_hit=False,
            modality="ocr",
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )
    ledger = getattr(getattr(ctx, "router", None), "usage_ledger", None)
    if ledger is None:
        return
    ledger.record(
        tier="ocr",
        cache_hit=False,
        prompt_chars=prompt_chars,
        completion_chars=completion_chars,
        client_id=client_id,
        model=model,
        provider="ocr",
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        reported_cost=0.0,
    )


def _apply_ocr_output_policy(
    data: dict[str, Any],
    engine: Any,
    *,
    metrics: Any = None,
) -> tuple[dict[str, Any] | None, Any]:
    """Run page markdown through output guardrails (ASR parity).

    Returns ``(payload, None)`` on success or ``(None, blocked_response)`` when
    a deny rule fires.
    """
    from daari.gateway.guardrails import (
        apply_endpoint_output_policy,
        endpoint_guardrail_blocked_response,
    )

    pages = data.get("pages")
    if not isinstance(pages, list):
        return data, None
    rewritten_pages: list[Any] = []
    for page in pages:
        if not isinstance(page, dict):
            rewritten_pages.append(page)
            continue
        markdown = str(page.get("markdown") or "")
        policy = apply_endpoint_output_policy(markdown, engine, metrics=metrics)
        if policy.blocked:
            return None, endpoint_guardrail_blocked_response(policy.block_message)
        rewritten_pages.append({**page, "markdown": policy.text})
    return {**data, "pages": rewritten_pages}, None


async def _run_vision(
    target: OcrTarget,
    *,
    model: str,
    source: str,
    doc_kind: str,
) -> dict[str, Any]:
    if doc_kind == "document_url" and not source.startswith("data:image"):
        # Local vision path is image-only; PDFs need a dedicated OCR base or L6.
        raise ValueError(
            "ocr.vision_model supports image_url (or image data URIs); "
            "use ocr.base_url or frontier for PDF document_url"
        )
    b64 = _image_b64_for_vision(source)
    if b64 is None:
        b64 = await _fetch_image_b64(source, timeout=target.timeout)
    url = f"{target.base_url.rstrip('/')}/api/chat"
    payload = {
        "model": model,
        "stream": False,
        "messages": [
            {
                "role": "user",
                "content": _OCR_PROMPT,
                "images": [b64],
            }
        ],
    }
    client = _shared_client()
    upstream = await client.post(url, json=payload, timeout=target.timeout)
    if upstream.status_code >= 400:
        upstream.raise_for_status()
    data = upstream.json()
    message = data.get("message") if isinstance(data, dict) else None
    content = ""
    if isinstance(message, dict):
        content = str(message.get("content") or "")
    elif isinstance(data, dict):
        content = str(data.get("response") or "")
    return _vision_pages_response(model=model, markdown=content.strip(), source=source)


async def handle_ocr(request: Request, body: OcrRequest) -> Any:
    from daari.gateway.idempotency import (
        abandon_slot,
        complete_json_slot,
        resolve_idempotency,
    )
    from daari.gateway.model_access import reject_disallowed_model, reject_frontier_passthrough

    invalid = _validate_document(body.document)
    if invalid is not None:
        return _error(400, "invalid_request_error", invalid)

    ctx = request.app.state.ctx
    settings = ctx.settings

    idem_kind, idem_response, idem_slot = await resolve_idempotency(request, ctx, body)
    if idem_kind in {"replay", "conflict"} and idem_response is not None:
        return idem_response

    pin = region_pin_from_request(request)
    try:
        targets = resolve_ocr_targets(settings, region_pin=pin)
    except RegionUnavailable as exc:
        log_gateway_event("ocr_region_unavailable", {"pin": exc.pin})
        abandon_slot(idem_slot)
        return _error(400, "region_unavailable", str(exc))
    if not targets:
        log_gateway_event("ocr_unavailable", {"reason": "no_local_or_frontier"})
        abandon_slot(idem_slot)
        return _error(503, "service_unavailable", _UNAVAILABLE)

    # Frontier-only path honors no_frontier / allowlist gates like other L6 modalities.
    if targets[0].via == "frontier":
        blocked = reject_frontier_passthrough(request)
        if blocked is not None:
            abandon_slot(idem_slot)
            return blocked

    model = (body.model or "").strip() or targets[0].default_model
    denied = reject_disallowed_model(request, model, settings)
    if denied is not None:
        abandon_slot(idem_slot)
        return denied

    assert body.document is not None
    doc_kind, source = _document_source(body.document)
    prompt_chars = len(source) + len(model)
    retry_settings = getattr(getattr(settings, "upstream", None), "retry", None)
    metrics = getattr(ctx, "metrics", None)
    from daari.gateway.guardrails import (
        apply_endpoint_input_policy,
        endpoint_guardrail_blocked_response,
        router_guardrails,
    )
    from daari.observability.metrics import genai_operation_name
    from daari.observability.otel import inject_trace_headers, modality_client_span

    engine = router_guardrails(ctx)
    # Screen document URL / data-URI text before dispatch (#1476).
    input_policy = apply_endpoint_input_policy(source, engine, metrics=metrics)
    if input_policy.blocked:
        abandon_slot(idem_slot)
        return endpoint_guardrail_blocked_response(input_policy.block_message)
    source = input_policy.text
    last_exc: Exception | None = None
    last_upstream: httpx.Response | None = None
    span_attrs = {
        "daari.modality": "ocr",
        "gen_ai.operation.name": genai_operation_name("ocr"),
        "gen_ai.request.model": model,
    }

    for target in targets:
        try:
            if target.via == "vision":
                with modality_client_span("daari.ocr", attributes=span_attrs):
                    data = await _run_vision(
                        target, model=model, source=source, doc_kind=doc_kind
                    )
                data, blocked = _apply_ocr_output_policy(data, engine, metrics=metrics)
                if blocked is not None:
                    abandon_slot(idem_slot)
                    return blocked
                assert data is not None
                log_gateway_event(
                    "ocr_ok", {"model": model, "via": "vision", "slot": target.slot_id}
                )
                caller = _caller_client_id(request)
                markdown = str(data["pages"][0].get("markdown") or "")
                _bind_spend_context(
                    request, ctx, model=model, client_id=caller, user_id=body.user
                )
                _record_request(
                    ctx,
                    client_id=caller,
                    model=model,
                    prompt_chars=prompt_chars,
                    completion_chars=len(markdown),
                )
                from daari.gateway.cost_headers import (
                    modality_response_headers,
                    session_id_from_request,
                )

                cost_headers = modality_response_headers(
                    ctx.settings,
                    tier="ocr",
                    model=model,
                    prompt_chars=prompt_chars,
                    input_tokens=max(0, prompt_chars // 4),
                    output_tokens=max(0, len(markdown) // 4),
                    cost_usd=0.0,
                    session_id=session_id_from_request(request),
                    savings=getattr(getattr(ctx, "router", None), "session_savings", None),
                )
                complete_json_slot(idem_slot, status_code=200, payload=data)
                return JSONResponse(data, headers=cost_headers)

            headers = {"Content-Type": "application/json"}
            if target.api_key:
                headers["Authorization"] = f"Bearer {target.api_key}"
            headers = inject_trace_headers(headers)
            url = f"{target.base_url.rstrip('/')}/ocr"
            payload = _ocr_payload(body, model)
            with modality_client_span("daari.ocr", attributes=span_attrs):
                upstream = await post_l6(
                    _shared_client(),
                    url,
                    headers=headers,
                    payload=payload,
                    timeout=target.timeout,
                    upstream="ocr",
                    retry=target.retry if target.retry is not None else retry_settings,
                    metrics=metrics,
                )
        except ValueError as exc:
            abandon_slot(idem_slot)
            return _error(400, "invalid_request_error", str(exc))
        except httpx.HTTPStatusError as exc:
            last_upstream = exc.response
            last_exc = exc
            log_gateway_event(
                "ocr_slot_error",
                {
                    "slot": target.slot_id,
                    "via": target.via,
                    "error": summarize_upstream_failure(exc),
                    "status": exc.response.status_code if exc.response is not None else None,
                },
            )
            continue
        except Exception as exc:
            last_exc = exc
            log_gateway_event(
                "ocr_slot_error",
                {
                    "slot": target.slot_id,
                    "via": target.via,
                    "error": summarize_upstream_failure(exc),
                },
            )
            continue

        if is_slot_failure(upstream):
            last_upstream = upstream
            log_gateway_event(
                "ocr_slot_http",
                {"slot": target.slot_id, "status": upstream.status_code, "via": target.via},
            )
            continue
        if upstream.status_code >= 400:
            log_gateway_event(
                "ocr_upstream_http",
                {"status": upstream.status_code, "slot": target.slot_id, "via": target.via},
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
            return _error(502, "bad_gateway", "OCR upstream returned non-JSON.")
        if not isinstance(data, dict):
            abandon_slot(idem_slot)
            return _error(502, "bad_gateway", "OCR upstream returned non-object JSON.")
        data, blocked = _apply_ocr_output_policy(data, engine, metrics=metrics)
        if blocked is not None:
            abandon_slot(idem_slot)
            return blocked
        assert data is not None
        log_gateway_event(
            "ocr_ok", {"model": model, "via": target.via, "slot": target.slot_id}
        )
        caller = _caller_client_id(request)
        pages = data.get("pages") if isinstance(data, dict) else None
        completion = 0
        if isinstance(pages, list):
            for page in pages:
                if isinstance(page, dict):
                    completion += len(str(page.get("markdown") or ""))
        _bind_spend_context(
            request, ctx, model=model, client_id=caller, user_id=body.user
        )
        _record_request(
            ctx,
            client_id=caller,
            model=model,
            prompt_chars=prompt_chars,
            completion_chars=completion,
        )
        from daari.gateway.cost_headers import modality_response_headers, session_id_from_request

        cost_headers = modality_response_headers(
            ctx.settings,
            tier="ocr",
            model=model,
            prompt_chars=prompt_chars,
            input_tokens=max(0, prompt_chars // 4),
            output_tokens=max(0, completion // 4),
            cost_usd=0.0,
            session_id=session_id_from_request(request),
            savings=getattr(getattr(ctx, "router", None), "session_savings", None),
        )
        complete_json_slot(idem_slot, status_code=200, payload=data)
        return JSONResponse(data, headers=cost_headers)

    if last_upstream is not None:
        log_gateway_event(
            "ocr_upstream_http",
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
            "ocr_upstream_error",
            {"error": summarize_upstream_failure(last_exc)},
        )
    abandon_slot(idem_slot)
    return _error(503, "upstream_error", "OCR upstream request failed.")
