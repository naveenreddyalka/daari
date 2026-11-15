"""Honor Responses ``truncation`` auto/disabled against known windows (#2215)."""

from __future__ import annotations

from typing import Any

from fastapi.responses import JSONResponse

from daari.gateway.internal import InternalRequest
from daari.gateway.request_log import log_gateway_event
from daari.router.compact_to_fit import compact_messages, estimate_tokens

_SUPPORTED = frozenset({"auto", "disabled"})


def context_length_exceeded_response(
    *,
    estimated: int,
    window: int,
) -> JSONResponse:
    message = (
        f"Your input exceeds the context window of this model "
        f"({estimated} estimated tokens > {window}). "
        f'Set truncation to "auto" to drop middle conversation items, '
        f'or shorten the input.'
    )
    return JSONResponse(
        status_code=400,
        content={
            "error": {
                "message": message,
                "type": "invalid_request_error",
                "param": "input",
                "code": "context_length_exceeded",
            }
        },
    )


def resolve_responses_window(
    request: InternalRequest,
    context_windows: dict[str, int] | None,
) -> int:
    """Pick the serving-tier window used for truncation checks.

    Prefer an explicit tier override / cap when present; otherwise L3 (the
    default local serving tier for ``model=daari``). Missing / non-positive
    windows mean "unknown" — callers skip enforcement.
    """
    windows = context_windows or {}
    for key in (
        getattr(request.meta, "tier_override", None),
        getattr(request.meta, "tier_cap", None),
        "L3",
    ):
        if not key:
            continue
        value = int(windows.get(str(key)) or 0)
        if value > 0:
            return value
    return 0


def apply_responses_truncation(
    request: InternalRequest,
    *,
    context_windows: dict[str, int] | None,
    metrics: Any | None = None,
) -> tuple[InternalRequest, JSONResponse | None]:
    """Compact or reject oversized Responses input per ``truncation``.

    ``truncation`` omitted or ``disabled`` → 400 when over the known window.
    ``auto`` → engage compact-to-fit against that window and record telemetry.
    Unknown windows leave the request unchanged (fail open on size).
    """
    mode = getattr(request.sampling, "truncation", None)
    if mode is not None and mode not in _SUPPORTED:
        return request, None
    effective = mode or "disabled"
    window = resolve_responses_window(request, context_windows)
    if window <= 0:
        return request, None

    estimated = estimate_tokens(request.messages)
    if estimated <= window:
        return request, None

    if effective == "disabled":
        log_gateway_event(
            "responses_truncation_rejected",
            {"truncation": effective, "estimated": estimated, "window": window},
        )
        return request, context_length_exceeded_response(
            estimated=estimated, window=window
        )

    # Message cap stays high so the token budget (model window) drives the trim.
    compacted, before, after = compact_messages(
        request.messages,
        enabled=True,
        max_messages=max(len(request.messages), 1),
        max_tokens=window,
    )
    tokens_before = estimated
    tokens_after = estimate_tokens(compacted)
    if tokens_after > window:
        log_gateway_event(
            "responses_truncation_rejected",
            {
                "truncation": "auto",
                "estimated": tokens_after,
                "window": window,
                "messages_before": before,
                "messages_after": after,
            },
        )
        return request, context_length_exceeded_response(
            estimated=tokens_after, window=window
        )

    if after >= before:
        # Nothing droppable — still over after a no-op compact.
        return request, context_length_exceeded_response(
            estimated=tokens_after, window=window
        )

    result = request.model_copy(deep=True)
    result.messages = compacted
    detail = {
        "messages_before": before,
        "messages_after": after,
        "tokens_before": tokens_before,
        "tokens_after": tokens_after,
    }
    result.meta.compact_to_fit = detail
    if metrics is not None and hasattr(metrics, "record_compact_to_fit_applied"):
        metrics.record_compact_to_fit_applied(
            tokens_dropped=max(0, tokens_before - tokens_after)
        )
    log_gateway_event("responses_truncation_auto", detail)
    return result, None
