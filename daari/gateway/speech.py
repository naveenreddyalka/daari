"""POST /v1/audio/speech — local-first OpenAI-compatible TTS (#847, #1888, #1909)."""

from __future__ import annotations

import time
from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass
from typing import Any

import httpx
from fastapi import Request
from fastapi.responses import JSONResponse, Response, StreamingResponse

from daari.gateway.client_errors import request_deadline_response, summarize_upstream_failure
from daari.gateway.disconnect import ClientDisconnected, await_unless_disconnected
from daari.gateway.request_log import log_gateway_event
from daari.router.deadline import (
    RequestDeadlineExceeded,
    aiter_with_ttft_deadline,
    bind_request_deadline,
    deadline_active,
    deadline_bounded_stream,
    nonstream_timeout,
    parse_deadline_ms,
    resolve_deadline_seconds,
)

_UNAVAILABLE = (
    "No local text-to-speech backend is configured. Set tts.base_url to an "
    "OpenAI-compatible server (the API root, including /v1)."
)

# OpenAI common voice ids → Ollama Phonon / Gradium catalog (#1909).
_OPENAI_TO_PHONON: dict[str, str] = {
    "alloy": "Zoey",
    "ash": "Easton",
    "ballad": "Easton",
    "coral": "Freya",
    "echo": "Easton",
    "fable": "Freya",
    "onyx": "Easton",
    "nova": "Zoey",
    "sage": "Easton",
    "shimmer": "Freya",
    "verse": "Zoey",
}

# Fallback when Ollama /api/show is unreachable (0.40.11+ ships a fuller catalog).
_PHONON_FALLBACK_VOICES: tuple[str, ...] = ("default", "Zoey", "Easton", "Freya")

_CONTENT_TYPES = {
    "mp3": "audio/mpeg",
    "opus": "audio/opus",
    "aac": "audio/aac",
    "flac": "audio/flac",
    "wav": "audio/wav",
    "pcm": "audio/pcm",
}

# Ollama Phonon accepts wav (default) and pcm only; other OpenAI formats → 400.
_PHONON_RESPONSE_FORMATS = frozenset({"wav", "pcm"})


def coerce_phonon_response_format(response_format: str) -> str:
    """Map OpenAI TTS formats onto Phonon-supported ``wav`` / ``pcm`` (#1952)."""
    fmt = (response_format or "").strip().lower() or "wav"
    if fmt in _PHONON_RESPONSE_FORMATS:
        return fmt
    return "wav"

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


def is_phonon_tts(target: TtsTarget, model_name: str = "") -> bool:
    """True when the configured TTS target is Ollama Phonon (#1909)."""
    blob = f"{target.model} {model_name}".lower()
    if "phonon" in blob:
        return True
    base = target.base_url.lower().rstrip("/")
    return base.endswith(":11434/v1") or base.endswith("/11434/v1")


def ollama_root_from_tts_base(base_url: str) -> str | None:
    """Strip a trailing ``/v1`` OpenAI root to the Ollama daemon root."""
    raw = (base_url or "").strip().rstrip("/")
    if raw.lower().endswith("/v1"):
        return raw[: -len("/v1")] or None
    return None


def phonon_fallback_voices() -> list[str]:
    return list(_PHONON_FALLBACK_VOICES)


def map_phonon_voice(
    voice: str,
    *,
    catalog: Mapping[str, str] | None = None,
) -> tuple[str | None, str | None]:
    """Map an OpenAI or Phonon voice name; return ``(name, error_message)``.

    ``catalog`` maps lowercased ids → canonical display names. When omitted,
    the built-in fallback catalog is used.
    """
    raw = (voice or "").strip()
    if not raw:
        raw = "alloy"
    catalog_map = {
        str(k).casefold(): str(v)
        for k, v in (catalog or {v: v for v in _PHONON_FALLBACK_VOICES}).items()
    }
    key = raw.casefold()
    if key in _OPENAI_TO_PHONON:
        mapped = _OPENAI_TO_PHONON[key]
        canon = catalog_map.get(mapped.casefold(), mapped)
        return canon, None
    if key in catalog_map:
        return catalog_map[key], None
    available = ", ".join(
        sorted({*_OPENAI_TO_PHONON.keys(), *catalog_map.values()}, key=str.casefold)
    )
    return None, (
        f"Unknown voice {raw!r}. Available voices: {available}. "
        "OpenAI names (alloy, echo, …) map onto the Phonon catalog."
    )


def build_voices_catalog(names: list[str]) -> dict[str, Any]:
    """OpenAI-shaped list payload for ``GET /v1/audio/voices``."""
    data = [
        {"id": name, "object": "voice", "owned_by": "daari"}
        for name in names
        if str(name or "").strip()
    ]
    return {"object": "list", "data": data}


async def fetch_phonon_voice_names(
    target: TtsTarget,
    *,
    model_name: str = "",
    client: httpx.AsyncClient | None = None,
) -> list[str]:
    """Load Phonon voices from Ollama ``/api/show``; fall back to built-ins."""
    root = ollama_root_from_tts_base(target.base_url)
    model = (target.model or model_name or "phonon").strip() or "phonon"
    if root:
        http = client or _shared_client()
        try:
            response = await http.post(
                f"{root}/api/show",
                json={"name": model},
                timeout=min(5.0, float(target.timeout or 5.0)),
            )
            if response.status_code < 400:
                payload = response.json()
                voices = payload.get("voices") if isinstance(payload, dict) else None
                if isinstance(voices, list) and voices:
                    names = [str(v).strip() for v in voices if str(v).strip()]
                    if names and "default" not in {n.casefold() for n in names}:
                        names = ["default", *names]
                    if names:
                        return names
        except Exception:
            log_gateway_event(
                "tts_phonon_voices_error",
                {"op": "api_show", "model": model},
            )
    return phonon_fallback_voices()


def tts_response_is_streaming(headers: Mapping[str, str] | httpx.Headers) -> bool:
    """True when upstream is delivering audio without a fixed Content-Length (#1888)."""
    try:
        te = str(headers.get("transfer-encoding") or headers.get("Transfer-Encoding") or "")
    except Exception:
        te = ""
    if "chunked" in te.lower():
        return True
    try:
        cl = headers.get("content-length") or headers.get("Content-Length")
    except Exception:
        cl = None
    if cl is None or str(cl).strip() == "":
        return True
    return False


async def post_speech(
    url: str,
    *,
    headers: dict[str, str],
    payload: dict[str, Any],
    timeout: float,
    retry: Any | None = None,
    metrics: Any | None = None,
) -> httpx.Response:
    from daari.router.retry import RETRYABLE_STATUS, RetryPolicy, run_upstream

    policy = (
        retry
        if isinstance(retry, RetryPolicy)
        else (RetryPolicy(attempts=1) if retry is None else RetryPolicy.from_settings(retry))
    )

    async def attempt() -> httpx.Response:
        response = await _shared_client().post(
            url, headers=headers, json=payload, timeout=timeout
        )
        if response.status_code in RETRYABLE_STATUS:
            response.raise_for_status()
        return response

    return await run_upstream(
        attempt,
        upstream="tts",
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
        metrics.record(
            "tts",
            cache_hit=False,
            latency_ms=latency_ms,
            modality="tts",
            input_tokens=max(0, len(input_text) // 4),
            output_tokens=max(0, audio_bytes // 4),
        )
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


async def handle_list_voices(request: Request) -> JSONResponse:
    """GET /v1/audio/voices — discover local / Phonon TTS voices (#1909)."""
    ctx = request.app.state.ctx
    target = resolve_tts_target(ctx.settings)
    if target is None:
        return _error(501, "tts_unavailable", _UNAVAILABLE)
    model_name = (target.model or "phonon").strip() or "phonon"
    if is_phonon_tts(target, model_name):
        names = await fetch_phonon_voice_names(target, model_name=model_name)
        # Also advertise OpenAI aliases clients already send.
        alias_targets = sorted(
            {_OPENAI_TO_PHONON[k] for k in _OPENAI_TO_PHONON}, key=str.casefold
        )
        # Prefer catalog order; append OpenAI alias labels as separate ids so
        # clients can still send alloy/echo while discovering Phonon names.
        seen: set[str] = set()
        ordered: list[str] = []
        for name in [*names, *sorted(_OPENAI_TO_PHONON.keys()), *alias_targets]:
            key = name.casefold()
            if key in seen:
                continue
            seen.add(key)
            ordered.append(name)
        return JSONResponse(build_voices_catalog(ordered))
    # Non-Phonon OpenAI-compatible TTS: advertise common OpenAI voice ids.
    return JSONResponse(build_voices_catalog(list(_OPENAI_TO_PHONON.keys())))


async def handle_speech(
    request: Request,
    *,
    model: str,
    input_text: str,
    voice: str | None,
    response_format: str,
    user: str | None = None,
    idem_slot: Any | None = None,
) -> Response | JSONResponse:
    from daari.gateway.idempotency import abandon_slot

    fmt = (response_format or "mp3").strip().lower() or "mp3"
    if fmt not in _CONTENT_TYPES:
        abandon_slot(idem_slot)
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
                    user=user,
                    idem_slot=idem_slot,
                )
        except RequestDeadlineExceeded as exc:
            abandon_slot(idem_slot)
            return request_deadline_response(exc)

    target = resolve_tts_target(ctx.settings)
    if target is None:
        abandon_slot(idem_slot)
        return _error(501, "tts_unavailable", _UNAVAILABLE)

    text = (input_text or "").strip()
    if not text:
        abandon_slot(idem_slot)
        return _error(400, "invalid_request_error", "input is required")

    max_chars = int(getattr(ctx.settings.tts, "max_input_chars", 4096) or 4096)
    if max_chars > 0 and len(text) > max_chars:
        abandon_slot(idem_slot)
        return _error(
            400,
            "invalid_request_error",
            f"input exceeds tts.max_input_chars ({max_chars})",
        )

    model_name = (target.model or (model or "")).strip()
    if not model_name:
        abandon_slot(idem_slot)
        return _error(400, "invalid_request_error", "model is required")

    from daari.gateway.model_access import reject_disallowed_model, reject_retired_model

    denied = reject_disallowed_model(request, model_name, ctx.settings)
    if denied is not None:
        abandon_slot(idem_slot)
        return denied
    retired = reject_retired_model(request, model_name, ctx.settings)
    if retired is not None:
        abandon_slot(idem_slot)
        return retired

    from daari.gateway.guardrails import (
        apply_endpoint_input_policy,
        endpoint_guardrail_blocked_response,
        router_guardrails,
    )

    policy = apply_endpoint_input_policy(
        text, router_guardrails(ctx), metrics=getattr(ctx, "metrics", None)
    )
    if policy.blocked:
        abandon_slot(idem_slot)
        return endpoint_guardrail_blocked_response(policy.block_message)
    text = policy.text

    voice_name = ((voice or "").strip() or target.voice or "alloy").strip()
    if is_phonon_tts(target, model_name):
        names = await fetch_phonon_voice_names(target, model_name=model_name)
        catalog = {n: n for n in names}
        mapped, voice_err = map_phonon_voice(voice_name, catalog=catalog)
        if voice_err is not None or mapped is None:
            abandon_slot(idem_slot)
            return _error(400, "invalid_request_error", voice_err or "Unknown voice")
        voice_name = mapped
        fmt = coerce_phonon_response_format(fmt)
    payload: dict[str, Any] = {
        "model": model_name,
        "input": text,
        "voice": voice_name,
        "response_format": fmt,
    }
    url = f"{target.base_url}/audio/speech"
    started = time.perf_counter()
    timeout = nonstream_timeout(target.timeout, "tts")
    from daari.observability.otel import inject_trace_headers

    trace_headers = inject_trace_headers({})
    try:
        return await await_unless_disconnected(
            request,
            _relay_speech(
                request,
                ctx=ctx,
                url=url,
                headers=trace_headers,
                payload=payload,
                timeout=timeout,
                started=started,
                model_name=model_name,
                voice_name=voice_name,
                fmt=fmt,
                text=text,
                user=user,
                idem_slot=idem_slot,
            ),
            metrics=ctx.metrics,
            phase="tts",
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
        abandon_slot(idem_slot)
        return _error(502, "tts_upstream_error", summarize_upstream_failure(exc))


def _speech_response_headers(
    request: Request,
    ctx: Any,
    *,
    model_name: str,
    text: str,
    audio_bytes: int,
) -> dict[str, str]:
    request_id = str(getattr(request.state, "request_id", None) or "")
    from daari.gateway.cost_headers import modality_response_headers, session_id_from_request

    headers = modality_response_headers(
        ctx.settings,
        tier="tts",
        model=model_name,
        prompt_chars=len(text),
        completion_chars=0,
        input_tokens=max(0, len(text) // 4),
        output_tokens=max(0, audio_bytes // 4),
        session_id=session_id_from_request(request),
        savings=getattr(getattr(ctx, "router", None), "session_savings", None),
    )
    if request_id:
        headers = {**headers, "X-Request-ID": request_id}
    return headers


def _finalize_speech(
    request: Request,
    ctx: Any,
    *,
    model_name: str,
    voice_name: str,
    fmt: str,
    text: str,
    audio: bytes,
    started: float,
    user: str | None,
    idem_slot: Any | None,
    media_type: str,
) -> None:
    from daari.gateway.idempotency import complete_binary_slot

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
    _bind_spend_context(
        request, ctx, model=model_name, client_id=caller, user_id=user
    )
    _record_request(
        ctx,
        client_id=caller,
        model=model_name,
        input_text=text,
        audio_bytes=len(audio),
        latency_ms=_elapsed_ms(started),
    )
    complete_binary_slot(
        idem_slot, status_code=200, data=audio, media_type=media_type
    )


async def _relay_speech(
    request: Request,
    *,
    ctx: Any,
    url: str,
    headers: dict[str, str],
    payload: dict[str, Any],
    timeout: float,
    started: float,
    model_name: str,
    voice_name: str,
    fmt: str,
    text: str,
    user: str | None,
    idem_slot: Any | None,
) -> Response | JSONResponse | StreamingResponse:
    from daari.gateway.idempotency import abandon_slot

    # Open the upstream stream manually so a StreamingResponse can keep it alive
    # until the client has drained chunks (async-with would close too early).
    stream_cm = deadline_bounded_stream(
        _shared_client(),
        "POST",
        url,
        headers=headers,
        json=payload,
        timeout=timeout,
    )
    upstream = await stream_cm.__aenter__()
    close_needed = True

    async def _close_upstream() -> None:
        nonlocal close_needed
        if not close_needed:
            return
        close_needed = False
        await stream_cm.__aexit__(None, None, None)

    try:
        if upstream.status_code < 200 or upstream.status_code >= 300:
            abandon_slot(idem_slot)
            try:
                await upstream.aread()
            except Exception:
                pass
            return _error(
                502,
                "tts_upstream_error",
                f"TTS upstream returned HTTP {upstream.status_code}",
            )

        media = upstream.headers.get("content-type") or _CONTENT_TYPES[fmt]
        media_type = media.split(";")[0].strip()

        if not tts_response_is_streaming(upstream.headers):
            audio = await upstream.aread() or b""
            if not audio:
                abandon_slot(idem_slot)
                return _error(
                    502, "tts_upstream_error", "TTS upstream returned an empty body"
                )
            _finalize_speech(
                request,
                ctx,
                model_name=model_name,
                voice_name=voice_name,
                fmt=fmt,
                text=text,
                audio=audio,
                started=started,
                user=user,
                idem_slot=idem_slot,
                media_type=media_type,
            )
            return Response(
                content=audio,
                media_type=media_type,
                headers=_speech_response_headers(
                    request,
                    ctx,
                    model_name=model_name,
                    text=text,
                    audio_bytes=len(audio),
                ),
            )

        # Streaming path: peek first byte so empty bodies stay 502 before headers.
        byte_iter = aiter_with_ttft_deadline(upstream.aiter_bytes()).__aiter__()
        try:
            first = await byte_iter.__anext__()
        except StopAsyncIteration:
            abandon_slot(idem_slot)
            return _error(
                502, "tts_upstream_error", "TTS upstream returned an empty body"
            )
        except RequestDeadlineExceeded:
            abandon_slot(idem_slot)
            raise

        while not first:
            try:
                first = await byte_iter.__anext__()
            except StopAsyncIteration:
                abandon_slot(idem_slot)
                return _error(
                    502, "tts_upstream_error", "TTS upstream returned an empty body"
                )

        collected = bytearray(first)
        close_needed = False  # generator owns shutdown

        async def _chunks() -> AsyncIterator[bytes]:
            try:
                yield first
                async for chunk in byte_iter:
                    if not chunk:
                        continue
                    collected.extend(chunk)
                    yield chunk
            finally:
                audio = bytes(collected)
                if audio:
                    _finalize_speech(
                        request,
                        ctx,
                        model_name=model_name,
                        voice_name=voice_name,
                        fmt=fmt,
                        text=text,
                        audio=audio,
                        started=started,
                        user=user,
                        idem_slot=idem_slot,
                        media_type=media_type,
                    )
                else:
                    abandon_slot(idem_slot)
                await stream_cm.__aexit__(None, None, None)

        # Output token count unknown until the stream ends; spend/metrics use the
        # collected size in finally. Headers use a prompt-based estimate.
        return StreamingResponse(
            _chunks(),
            media_type=media_type,
            headers=_speech_response_headers(
                request,
                ctx,
                model_name=model_name,
                text=text,
                audio_bytes=max(0, len(text) // 4),
            ),
        )
    finally:
        await _close_upstream()
