"""POST /v1/audio/speech — local-first OpenAI-compatible TTS (#847)."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import httpx
from fastapi import Request
from fastapi.responses import JSONResponse, Response

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
    "No local text-to-speech backend is configured. Set tts.base_url to an "
    "OpenAI-compatible server (the API root, including /v1)."
)

_CONTENT_TYPES = {
    "mp3": "audio/mpeg",
    "opus": "audio/opus",
    "aac": "audio/aac",
    "flac": "audio/flac",
    "wav": "audio/wav",
    "pcm": "audio/pcm",
}

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
class TtsTarget:
    base_url: str
    model: str
    voice: str
    timeout: float


def _error(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"error": {"type": code, "message": message}},
    )


def resolve_tts_target(settings: Any) -> TtsTarget | None:
    tts = getattr(settings, "tts", None)
    if tts is None:
        return None
    base = str(getattr(tts, "base_url", "") or "").strip().rstrip("/")
    if not base:
        return None
    upstream = getattr(settings, "upstream", None)
    timeout = float(getattr(upstream, "local_timeout_seconds", 120.0) or 120.0)
    return TtsTarget(
        base_url=base,
        model=str(getattr(tts, "model", "") or "").strip(),
        voice=str(getattr(tts, "voice", "") or "").strip(),
        timeout=timeout,
    )


async def post_speech(
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
    input_text: str,
    audio_bytes: int,
    latency_ms: int,
) -> None:
    metrics = getattr(ctx, "metrics", None)
    if metrics is not None and hasattr(metrics, "record"):
        metrics.record("tts", cache_hit=False, latency_ms=latency_ms)
    ledger = getattr(getattr(ctx, "router", None), "usage_ledger", None)
    if ledger is None:
        return
    ledger.record(
        tier="tts",
        cache_hit=False,
        prompt_chars=len(input_text),
        completion_chars=0,
        client_id=client_id,
        model=model,
        provider="tts",
        input_tokens=max(0, len(input_text) // 4),
        output_tokens=max(0, audio_bytes // 4),
    )


def _audio_deadline_seconds(request: Request, settings: Any) -> float | None:
    header_ms = parse_deadline_ms(request.headers.get("x-daari-deadline-ms"))
    upstream = getattr(settings, "upstream", None)
    setting = getattr(upstream, "request_deadline_seconds", None) if upstream else None
    return resolve_deadline_seconds(header_ms, setting)


async def handle_speech(
    request: Request,
    *,
    model: str,
    input_text: str,
    voice: str | None,
    response_format: str,
) -> Response | JSONResponse:
    fmt = (response_format or "mp3").strip().lower() or "mp3"
    if fmt not in _CONTENT_TYPES:
        return _error(
            400,
            "invalid_request_error",
            f"response_format must be one of: {', '.join(sorted(_CONTENT_TYPES))}",
        )
    ctx = request.app.state.ctx
    seconds = _audio_deadline_seconds(request, ctx.settings)
    if seconds is not None and not deadline_active():
        try:
            with bind_request_deadline(seconds, metrics=ctx.metrics):
                return await handle_speech(
                    request,
                    model=model,
                    input_text=input_text,
                    voice=voice,
                    response_format=response_format,
                )
        except RequestDeadlineExceeded as exc:
            return request_deadline_response(exc)

    target = resolve_tts_target(ctx.settings)
    if target is None:
        return _error(501, "tts_unavailable", _UNAVAILABLE)

    text = (input_text or "").strip()
    if not text:
        return _error(400, "invalid_request_error", "input is required")

    model_name = (target.model or (model or "")).strip()
    if not model_name:
        return _error(400, "invalid_request_error", "model is required")

    from daari.gateway.model_access import reject_disallowed_model

    denied = reject_disallowed_model(request, model_name, ctx.settings)
    if denied is not None:
        return denied

    voice_name = ((voice or "").strip() or target.voice or "alloy").strip()
    payload: dict[str, Any] = {
        "model": model_name,
        "input": text,
        "voice": voice_name,
        "response_format": fmt,
    }
    url = f"{target.base_url}/audio/speech"
    started = time.perf_counter()
    try:
        timeout = nonstream_timeout(target.timeout, "tts")
        from daari.observability.otel import inject_trace_headers

        upstream = await await_unless_disconnected(
            request,
            post_speech(
                url,
                headers=inject_trace_headers({}),
                payload=payload,
                timeout=timeout,
            ),
            metrics=ctx.metrics,
            phase="tts",
            model=model_name,
        )
    except RequestDeadlineExceeded as exc:
        return request_deadline_response(exc)
    except ClientDisconnected:
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
        return _error(502, "tts_upstream_error", summarize_upstream_failure(exc))
    latency_ms = _elapsed_ms(started)

    if upstream.status_code < 200 or upstream.status_code >= 300:
        return _error(
            502,
            "tts_upstream_error",
            f"TTS upstream returned HTTP {upstream.status_code}",
        )
    audio = upstream.content or b""
    if not audio:
        return _error(502, "tts_upstream_error", "TTS upstream returned an empty body")

    log_gateway_event(
        "audio_speech",
        {
            "model": model_name,
            "voice": voice_name,
            "format": fmt,
            "bytes": len(audio),
            "chars": len(text),
        },
    )
    caller = _caller_client_id(request)
    _bind_spend_context(request, ctx, model=model_name, client_id=caller)
    _record_request(
        ctx,
        client_id=caller,
        model=model_name,
        input_text=text,
        audio_bytes=len(audio),
        latency_ms=latency_ms,
    )
    media = upstream.headers.get("content-type") or _CONTENT_TYPES[fmt]
    request_id = str(getattr(request.state, "request_id", None) or "")
    headers = {"X-Request-ID": request_id} if request_id else None
    return Response(
        content=audio,
        media_type=media.split(";")[0].strip(),
        headers=headers,
    )
