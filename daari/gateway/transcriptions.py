"""POST /v1/audio/transcriptions — local-first OpenAI-compatible ASR (#715)."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import httpx
from fastapi import Request, UploadFile
from fastapi.responses import JSONResponse

from daari.gateway.client_errors import summarize_upstream_failure
from daari.gateway.disconnect import ClientDisconnected, await_unless_disconnected
from daari.gateway.request_log import log_gateway_event

_UNAVAILABLE = (
    "No local speech-to-text backend is configured. Set asr.base_url to an "
    "OpenAI-compatible server (the API root, including /v1). Cloud upload stays "
    "off unless asr.frontier_fallback is true, frontier.enabled is true, and a "
    "frontier API key is set."
)


@dataclass(frozen=True)
class AsrTarget:
    base_url: str
    api_key: str | None
    model: str
    via: str
    timeout: float


def _error(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"error": {"type": code, "message": message}},
    )


def resolve_asr_target(settings: Any) -> AsrTarget | None:
    """Local ASR when configured; otherwise one explicit frontier fallback."""
    asr = getattr(settings, "asr", None)
    if asr is None:
        return None
    base = str(getattr(asr, "base_url", "") or "").strip().rstrip("/")
    model = str(getattr(asr, "model", "") or "").strip()
    if base:
        upstream = getattr(settings, "upstream", None)
        timeout = float(getattr(upstream, "local_timeout_seconds", 120.0) or 120.0)
        return AsrTarget(base_url=base, api_key=None, model=model, via="local", timeout=timeout)
    if not bool(getattr(asr, "frontier_fallback", False)):
        return None
    frontier = getattr(settings, "frontier", None)
    if frontier is None or not bool(getattr(frontier, "enabled", False)):
        return None
    from daari.router.frontier_pool import build_frontier_pool
    from daari.security.secret_refs import SecretRefError

    pool = build_frontier_pool(settings)
    if not pool.slots:
        return None
    slot = pool.slots[0]
    try:
        key = slot.pick_key()
    except SecretRefError:
        return None
    secret = str(key or "").strip()
    if not secret:
        return None
    slot_base = str(getattr(slot.executor, "base_url", "") or "").strip().rstrip("/")
    if not slot_base:
        return None
    timeout = float(getattr(slot.executor, "timeout", 90.0) or 90.0)
    return AsrTarget(
        base_url=slot_base,
        api_key=secret,
        model=model,
        via="frontier",
        timeout=timeout,
    )


async def post_transcription(
    url: str,
    *,
    headers: dict[str, str],
    filename: str,
    content: bytes,
    content_type: str,
    form: dict[str, str],
    timeout: float,
) -> httpx.Response:
    files = {
        "file": (
            filename or "audio",
            content,
            content_type or "application/octet-stream",
        )
    }
    async with httpx.AsyncClient(timeout=timeout) as client:
        return await client.post(url, headers=headers, data=form, files=files)


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
) -> None:
    tier = "L6" if via == "frontier" else "asr"
    provider = "frontier" if via == "frontier" else "asr"
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
    target = resolve_asr_target(ctx.settings)
    if target is None:
        return _error(501, "asr_unavailable", _UNAVAILABLE)

    model_name = (target.model or (model or "")).strip()
    if not model_name:
        return _error(400, "invalid_request_error", "model is required")

    from daari.gateway.model_access import reject_disallowed_model

    denied = reject_disallowed_model(request, model_name, ctx.settings)
    if denied is not None:
        return denied

    content = await file.read()
    if not content:
        return _error(400, "invalid_request_error", "file is empty")

    form: dict[str, str] = {"model": model_name, "response_format": "json"}
    lang = (language or "").strip()
    if lang:
        form["language"] = lang
    hint = (prompt or "").strip()
    if hint:
        form["prompt"] = hint
    headers: dict[str, str] = {}
    if target.api_key:
        headers["Authorization"] = f"Bearer {target.api_key}"

    url = f"{target.base_url}/{upstream_path.lstrip('/')}"
    started = time.perf_counter()
    phase = "translation" if upstream_path.rstrip("/").endswith("translations") else "asr"
    try:
        upstream = await await_unless_disconnected(
            request,
            post_transcription(
                url,
                headers=headers,
                filename=file.filename or "audio",
                content=content,
                content_type=file.content_type or "application/octet-stream",
                form=form,
                timeout=target.timeout,
            ),
            metrics=ctx.metrics,
            phase=phase,
            model=model_name,
        )
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
        return _error(502, "asr_upstream_error", summarize_upstream_failure(exc))
    latency_ms = _elapsed_ms(started)

    if upstream.status_code < 200 or upstream.status_code >= 300:
        return _error(
            502,
            "asr_upstream_error",
            f"ASR upstream returned HTTP {upstream.status_code}",
        )
    try:
        payload = upstream.json()
    except Exception:
        return _error(502, "asr_upstream_error", "ASR upstream returned a non-JSON body")
    if not isinstance(payload, dict) or not isinstance(payload.get("text"), str):
        return _error(
            502,
            "asr_upstream_error",
            "ASR upstream JSON did not include text",
        )

    log_gateway_event(
        event,
        {
            "model": model_name,
            "bytes": len(content),
            "via": target.via,
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
    )
    return payload


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
