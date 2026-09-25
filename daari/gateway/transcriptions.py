"""POST /v1/audio/transcriptions — local-first OpenAI-compatible ASR (#715)."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import httpx
from fastapi import Request, UploadFile
from fastapi.responses import JSONResponse

from daari.gateway.client_errors import request_deadline_response, summarize_upstream_failure
from daari.gateway.disconnect import ClientDisconnected, await_unless_disconnected
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
    "No local speech-to-text backend is configured. Set asr.base_url to an "
    "OpenAI-compatible server (the API root, including /v1). Cloud upload stays "
    "off unless asr.frontier_fallback is true, frontier.enabled is true, and a "
    "frontier API key is set."
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
class AsrTarget:
    base_url: str
    api_key: str | None
    model: str
    via: str
    timeout: float
    slot_id: str = ""
    retry: Any | None = None


def _error(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"error": {"type": code, "message": message}},
    )


def resolve_asr_targets(
    settings: Any, *, region_pin: str | None = None
) -> list[AsrTarget]:
    """Local ASR when configured; else frontier slots in pool order (#1061).

    Raises RegionUnavailable when a pin is set but no slot can satisfy it.
    """
    asr = getattr(settings, "asr", None)
    if asr is None:
        return []
    base = str(getattr(asr, "base_url", "") or "").strip().rstrip("/")
    model = str(getattr(asr, "model", "") or "").strip()
    if base:
        upstream = getattr(settings, "upstream", None)
        timeout = float(getattr(upstream, "local_timeout_seconds", 120.0) or 120.0)
        return [
            AsrTarget(
                base_url=base,
                api_key=None,
                model=model,
                via="local",
                timeout=timeout,
            )
        ]
    if not bool(getattr(asr, "frontier_fallback", False)):
        return []
    from daari.gateway.l6_passthrough import resolve_l6_targets

    l6 = resolve_l6_targets(
        settings, region_pin=region_pin, default_model=model or "whisper-1"
    )
    return [
        AsrTarget(
            base_url=target.base_url,
            api_key=target.api_key,
            model=model or target.default_model,
            via="frontier",
            timeout=target.timeout,
            slot_id=target.slot_id,
            retry=target.retry,
        )
        for target in l6
    ]


def resolve_asr_target(
    settings: Any, *, region_pin: str | None = None
) -> AsrTarget | None:
    """Local ASR when configured; otherwise the first eligible frontier slot."""
    from daari.gateway.l6_passthrough import RegionUnavailable

    try:
        targets = resolve_asr_targets(settings, region_pin=region_pin)
    except RegionUnavailable:
        return None
    return targets[0] if targets else None


_AUDIO_CONTENT_TYPES = {
    "wav": ("audio/wav", "clip.wav"),
    "mp3": ("audio/mpeg", "clip.mp3"),
}


async def inject_inline_audio_transcripts(request: Any, settings: Any) -> Any:
    """When ``asr.base_url`` is set, transcribe ``Message.audio`` into text (#981).

    Frontier still receives the original ``input_audio`` blocks; local tiers get
    the transcript appended to ``content`` so the turn stays on-box.
    """
    from daari.gateway.internal import Message

    if not any(getattr(message, "audio", None) for message in request.messages):
        return request
    asr = getattr(settings, "asr", None)
    base = str(getattr(asr, "base_url", "") or "").strip().rstrip("/") if asr else ""
    if not base:
        return request
    target = resolve_asr_target(settings)
    if target is None or target.via != "local":
        return request

    import base64

    from daari.gateway.request_log import log_gateway_event

    updated: list[Message] = []
    changed = False
    for message in request.messages:
        clips = list(getattr(message, "audio", None) or [])
        if not clips:
            updated.append(message)
            continue
        transcripts: list[str] = []
        for clip in clips:
            raw = getattr(clip, "data", None)
            if not isinstance(raw, str) or not raw.strip():
                continue
            try:
                content = base64.b64decode(raw, validate=False)
            except Exception:
                log_gateway_event("input_audio_decode_failed", {"format": clip.format})
                continue
            fmt = str(getattr(clip, "format", "") or "wav").lower()
            content_type, filename = _AUDIO_CONTENT_TYPES.get(fmt, ("application/octet-stream", "clip.bin"))
            form: dict[str, str] = {"response_format": "json"}
            if target.model:
                form["model"] = target.model
            headers: dict[str, str] = {}
            if target.api_key:
                headers["Authorization"] = f"Bearer {target.api_key}"
            try:
                upstream = getattr(settings, "upstream", None)
                retry = getattr(upstream, "retry", None) if upstream is not None else None
                response = await post_transcription(
                    f"{target.base_url}/audio/transcriptions",
                    headers=headers,
                    filename=filename,
                    content=content,
                    content_type=content_type,
                    form=form,
                    timeout=target.timeout,
                    retry=retry,
                )
                response.raise_for_status()
                body = response.json()
                text = body.get("text") if isinstance(body, dict) else None
                if isinstance(text, str) and text.strip():
                    transcripts.append(text.strip())
            except Exception as exc:
                log_gateway_event(
                    "input_audio_asr_failed",
                    {"error": summarize_upstream_failure(exc), "format": fmt},
                )
        if not transcripts:
            updated.append(message)
            continue
        joined = "\n".join(transcripts)
        existing = (message.content or "").strip()
        new_content = f"{existing}\n{joined}".strip() if existing else joined
        updated.append(message.model_copy(update={"content": new_content}))
        changed = True
        log_gateway_event(
            "input_audio_asr_injected",
            {"clips": len(clips), "chars": len(joined)},
        )
    if not changed:
        return request
    return request.model_copy(update={"messages": updated})


async def post_transcription(
    url: str,
    *,
    headers: dict[str, str],
    filename: str,
    content: bytes,
    content_type: str,
    form: dict[str, str],
    timeout: float,
    retry: Any | None = None,
    metrics: Any | None = None,
) -> httpx.Response:
    from daari.router.retry import RETRYABLE_STATUS, RetryPolicy, run_upstream

    files = {
        "file": (
            filename or "audio",
            content,
            content_type or "application/octet-stream",
        )
    }
    policy = (
        retry
        if isinstance(retry, RetryPolicy)
        else (RetryPolicy(attempts=1) if retry is None else RetryPolicy.from_settings(retry))
    )

    async def attempt() -> httpx.Response:
        response = await _shared_client().post(
            url, headers=headers, data=form, files=files, timeout=timeout
        )
        if response.status_code in RETRYABLE_STATUS:
            response.raise_for_status()
        return response

    return await run_upstream(
        attempt,
        upstream="asr",
        policy=policy,
        timeout=timeout,
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
    """Copy virtual-key identity onto the chargeback row before the usage hook fires."""
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
    via: str,
    text: str,
    latency_ms: int,
    local_tier: str = "asr",
) -> None:
    tier = "L6" if via == "frontier" else local_tier
    provider = "frontier" if via == "frontier" else local_tier
    metrics = getattr(ctx, "metrics", None)
    if metrics is not None and hasattr(metrics, "record"):
        metrics.record(tier, cache_hit=False, latency_ms=latency_ms)
    ledger = getattr(getattr(ctx, "router", None), "usage_ledger", None)
    if ledger is None:
        return
    ledger.record(
        tier=tier,
        cache_hit=False,
        completion_chars=len(text),
        client_id=client_id,
        model=model,
        provider=provider,
        input_tokens=0,
        output_tokens=max(0, len(text) // 4),
    )


def _audio_deadline_seconds(request: Request, settings: Any) -> float | None:
    header_ms = parse_deadline_ms(request.headers.get("x-daari-deadline-ms"))
    upstream = getattr(settings, "upstream", None)
    setting = getattr(upstream, "request_deadline_seconds", None) if upstream else None
    return resolve_deadline_seconds(header_ms, setting)


async def handle_transcription(
    request: Request,
    *,
    file: UploadFile,
    model: str,
    language: str | None,
    prompt: str | None,
    response_format: str,
    upstream_path: str = "audio/transcriptions",
    event: str = "audio_transcription",
) -> JSONResponse | dict[str, Any]:
    fmt = (response_format or "json").strip().lower() or "json"
    if fmt != "json":
        return _error(
            400,
            "invalid_request_error",
            "response_format must be json",
        )
    ctx = request.app.state.ctx
    seconds = _audio_deadline_seconds(request, ctx.settings)
    if seconds is not None and not deadline_active():
        try:
            with bind_request_deadline(seconds, metrics=ctx.metrics):
                return await handle_transcription(
                    request,
                    file=file,
                    model=model,
                    language=language,
                    prompt=prompt,
                    response_format=response_format,
                    upstream_path=upstream_path,
                    event=event,
                )
        except RequestDeadlineExceeded as exc:
            return request_deadline_response(exc)

    from daari.gateway.l6_passthrough import (
        RegionUnavailable,
        is_slot_failure,
        region_pin_from_request,
    )
    from daari.gateway.model_access import reject_disallowed_model, reject_frontier_passthrough

    pin = region_pin_from_request(request)
    try:
        targets = resolve_asr_targets(ctx.settings, region_pin=pin)
    except RegionUnavailable as exc:
        log_gateway_event("asr_region_unavailable", {"pin": exc.pin})
        return _error(400, "region_unavailable", str(exc))
    if not targets:
        return _error(501, "asr_unavailable", _UNAVAILABLE)

    # Frontier ASR leaves the box — honor the same L6 fence as other passthroughs.
    if any(t.via == "frontier" for t in targets):
        blocked = reject_frontier_passthrough(request)
        if blocked is not None:
            return blocked

    model_name = (targets[0].model or (model or "")).strip()
    if not model_name:
        return _error(400, "invalid_request_error", "model is required")

    denied = reject_disallowed_model(request, model_name, ctx.settings)
    if denied is not None:
        return denied

    from daari.gateway.guardrails import (
        apply_endpoint_input_policy,
        apply_endpoint_output_policy,
        endpoint_guardrail_blocked_response,
        router_guardrails,
    )

    engine = router_guardrails(ctx)
    metrics = getattr(ctx, "metrics", None)
    hint = (prompt or "").strip()
    if hint:
        prompt_policy = apply_endpoint_input_policy(hint, engine, metrics=metrics)
        if prompt_policy.blocked:
            return endpoint_guardrail_blocked_response(prompt_policy.block_message)
        hint = prompt_policy.text

    content = await file.read()
    if not content:
        return _error(400, "invalid_request_error", "file is empty")

    form: dict[str, str] = {"model": model_name, "response_format": "json"}
    lang = (language or "").strip()
    if lang:
        form["language"] = lang
    if hint:
        form["prompt"] = hint

    from daari.gateway.idempotency import (
        abandon_slot,
        complete_json_slot,
        multipart_body_hash,
        resolve_idempotency,
    )

    # Hash via the public multipart helper so form key order and file digest match tests.
    idem_payload = {
        "path": upstream_path,
        "digest": multipart_body_hash(
            fields=form, file_bytes=content, filename=file.filename or ""
        ),
    }
    idem_kind, idem_response, idem_slot = await resolve_idempotency(
        request, ctx, idem_payload
    )
    if idem_kind in {"replay", "conflict"} and idem_response is not None:
        return idem_response

    from daari.observability.otel import inject_trace_headers

    started = time.perf_counter()
    phase = "translation" if upstream_path.rstrip("/").endswith("translations") else "asr"
    retry_settings = getattr(getattr(ctx.settings, "upstream", None), "retry", None)
    last_exc: Exception | None = None
    last_status: int | None = None
    target = targets[0]
    upstream: httpx.Response | None = None

    for target in targets:
        headers: dict[str, str] = {}
        if target.api_key:
            headers["Authorization"] = f"Bearer {target.api_key}"
        headers = inject_trace_headers(headers)
        url = f"{target.base_url}/{upstream_path.lstrip('/')}"
        try:
            timeout = nonstream_timeout(target.timeout, phase)
            slot_retry = target.retry if target.retry is not None else retry_settings
            upstream = await await_unless_disconnected(
                request,
                post_transcription(
                    url,
                    headers=headers,
                    filename=file.filename or "audio",
                    content=content,
                    content_type=file.content_type or "application/octet-stream",
                    form=form,
                    timeout=timeout,
                    retry=slot_retry,
                    metrics=ctx.metrics,
                ),
                metrics=ctx.metrics,
                phase=phase,
                model=model_name,
            )
        except RequestDeadlineExceeded as exc:
            abandon_slot(idem_slot)
            return request_deadline_response(exc)
        except ClientDisconnected:
            abandon_slot(idem_slot)
            return JSONResponse(
                status_code=499,
                content={
                    "error": {
                        "type": "client_disconnected",
                        "message": "client disconnected.",
                    }
                },
            )
        except httpx.HTTPError as exc:
            last_exc = exc
            log_gateway_event(
                "asr_slot_error",
                {
                    "slot": target.slot_id,
                    "error": summarize_upstream_failure(exc),
                    "via": target.via,
                },
            )
            if target.via != "frontier" or target is targets[-1]:
                abandon_slot(idem_slot)
                return _error(502, "asr_upstream_error", summarize_upstream_failure(exc))
            continue
        if target.via == "frontier" and is_slot_failure(upstream) and target is not targets[-1]:
            last_status = upstream.status_code
            log_gateway_event(
                "asr_slot_http",
                {"slot": target.slot_id, "status": upstream.status_code},
            )
            continue
        break
    else:
        if last_status is not None:
            abandon_slot(idem_slot)
            return _error(
                502,
                "asr_upstream_error",
                f"ASR upstream returned HTTP {last_status}",
            )
        if last_exc is not None:
            abandon_slot(idem_slot)
            return _error(502, "asr_upstream_error", summarize_upstream_failure(last_exc))
        abandon_slot(idem_slot)
        return _error(502, "asr_upstream_error", "ASR upstream request failed")

    assert upstream is not None
    latency_ms = _elapsed_ms(started)

    if upstream.status_code < 200 or upstream.status_code >= 300:
        abandon_slot(idem_slot)
        return _error(
            502,
            "asr_upstream_error",
            f"ASR upstream returned HTTP {upstream.status_code}",
        )
    try:
        payload = upstream.json()
    except Exception:
        abandon_slot(idem_slot)
        return _error(502, "asr_upstream_error", "ASR upstream returned a non-JSON body")
    if not isinstance(payload, dict) or not isinstance(payload.get("text"), str):
        abandon_slot(idem_slot)
        return _error(
            502,
            "asr_upstream_error",
            "ASR upstream JSON did not include text",
        )

    out_policy = apply_endpoint_output_policy(payload["text"], engine, metrics=metrics)
    if out_policy.blocked:
        abandon_slot(idem_slot)
        return endpoint_guardrail_blocked_response(out_policy.block_message)
    payload = {**payload, "text": out_policy.text}

    log_gateway_event(
        event,
        {
            "model": model_name,
            "bytes": len(content),
            "via": target.via,
            "slot": target.slot_id or None,
        },
    )
    caller = _caller_client_id(request)
    _bind_spend_context(request, ctx, model=model_name, client_id=caller)
    _record_request(
        ctx,
        client_id=caller,
        model=model_name,
        via=target.via,
        text=payload["text"],
        latency_ms=latency_ms,
        local_tier=phase,
    )
    from daari.gateway.cost_headers import modality_response_headers, session_id_from_request

    tier = "L6" if target.via == "frontier" else phase
    out_tokens = max(0, len(payload["text"]) // 4)
    headers = modality_response_headers(
        ctx.settings,
        tier=tier,
        model=model_name,
        prompt_chars=0,
        completion_chars=len(payload["text"]),
        input_tokens=0,
        output_tokens=out_tokens,
        executor="frontier" if target.via == "frontier" else phase,
        session_id=session_id_from_request(request),
        savings=getattr(getattr(ctx, "router", None), "session_savings", None),
    )
    request_id = str(getattr(request.state, "request_id", None) or "")
    if request_id:
        headers = {**headers, "X-Request-ID": request_id}
    complete_json_slot(idem_slot, status_code=200, payload=payload)
    return JSONResponse(payload, headers=headers)


async def handle_translation(
    request: Request,
    *,
    file: UploadFile,
    model: str,
    prompt: str | None,
    response_format: str,
) -> JSONResponse | dict[str, Any]:
    """POST /v1/audio/translations — same local ASR target, translations path (#758)."""
    return await handle_transcription(
        request,
        file=file,
        model=model,
        language=None,
        prompt=prompt,
        response_format=response_format,
        upstream_path="audio/translations",
        event="audio_translation",
    )
