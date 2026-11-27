"""Client-facing gateway error text that never leaks registered secrets (#412)."""

from __future__ import annotations

import httpx

from daari.security.secret_refs import redact_secrets


def safe_detail(exc_or_text: BaseException | str, *, prefix: str = "") -> str:
    """Redact registered secrets from an exception message or plain string."""
    text = exc_or_text if isinstance(exc_or_text, str) else str(exc_or_text)
    return redact_secrets(f"{prefix}{text}")


def _upstream_host(exc: BaseException) -> str:
    request = getattr(exc, "request", None)
    url = getattr(request, "url", None)
    host = getattr(url, "host", None) if url is not None else None
    if host:
        return str(host)
    return "upstream"


def summarize_upstream_failure(exc: BaseException) -> str:
    """Provider + status (or error class) — never raw URLs or response bodies."""
    if isinstance(exc, httpx.HTTPStatusError):
        status = getattr(getattr(exc, "response", None), "status_code", "?")
        return f"{_upstream_host(exc)} returned HTTP {status}"
    if isinstance(exc, httpx.RequestError):
        return f"request to {_upstream_host(exc)} failed ({type(exc).__name__})"
    cause = exc.__cause__ or exc.__context__
    if isinstance(cause, (httpx.HTTPStatusError, httpx.RequestError)):
        return summarize_upstream_failure(cause)
    return str(exc)


def routing_failure_detail(exc: BaseException) -> str:
    """503 `Routing failed:` detail for gateway catch-alls."""
    return safe_detail(summarize_upstream_failure(exc), prefix="Routing failed: ")


def _exception_chain(exc: BaseException):
    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        yield current
        cause = current.__cause__
        current = cause if isinstance(cause, BaseException) else None


def is_upstream_overload(exc: BaseException) -> bool:
    """True when the terminal cause is HTTP 429 or 529 (circuit-breaker overload)."""
    from daari.router.retry import status_of

    return any(status_of(item) in {429, 529} for item in _exception_chain(exc))


def overload_retry_after_seconds(exc: BaseException) -> int:
    """Upstream ``Retry-After`` when present, otherwise one second."""
    from daari.router.retry import retry_after_seconds

    for item in _exception_chain(exc):
        seconds = retry_after_seconds(item)
        if seconds:
            return max(1, int(seconds))
    return 1


def overload_json_response(exc: BaseException, *, anthropic: bool = False):
    """Typed overload envelope, or None when this failure is not overload."""
    if not is_upstream_overload(exc):
        return None
    from fastapi.responses import JSONResponse

    message = routing_failure_detail(exc)
    headers = {"Retry-After": str(overload_retry_after_seconds(exc))}
    if anthropic:
        return JSONResponse(
            status_code=529,
            content={
                "type": "error",
                "error": {"type": "overloaded_error", "message": message},
            },
            headers=headers,
        )
    return JSONResponse(
        status_code=503,
        content={"error": {"type": "server_is_overloaded", "message": message}},
        headers=headers,
    )


def overload_stream_frame(exc: BaseException, *, anthropic: bool = False) -> str | None:
    """SSE error frame for a terminal overload, or None for other failures."""
    if not is_upstream_overload(exc):
        return None
    import json

    message = routing_failure_detail(exc)
    if anthropic:
        payload = {
            "type": "error",
            "error": {"type": "overloaded_error", "message": message},
        }
        return f"event: error\ndata: {json.dumps(payload)}\n\n"
    payload = {"error": {"type": "server_is_overloaded", "message": message}}
    return "data: " + json.dumps(payload) + "\n\n"


def request_deadline_response(exc: BaseException):
    """504 JSON body that names the request deadline."""
    from fastapi.responses import JSONResponse

    return JSONResponse(
        status_code=504,
        content={
            "error": {
                "type": "request_deadline_exceeded",
                "message": str(exc),
                "deadline_seconds": getattr(exc, "deadline_seconds", None),
            }
        },
    )


def backend_unavailable_message(exc: BaseException) -> str:
    return safe_detail(exc)
