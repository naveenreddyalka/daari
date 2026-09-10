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


def backend_unavailable_message(exc: BaseException) -> str:
    return safe_detail(exc)
