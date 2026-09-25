"""Early request-body size cap (#933).

Reject oversized bodies with 413 before middleware buffers them into RAM —
important on a box that also hosts local models.
"""

from __future__ import annotations

from typing import Any

from fastapi.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from daari.gateway.request_log import log_gateway_event

DEFAULT_MAX_BODY_BYTES = 10 * 1024 * 1024
# File / audio uploads may exceed the chat JSON cap; still bound memory.
UPLOAD_ROUTE_FLOOR_BYTES = 100 * 1024 * 1024

OPEN_BODY_PATHS = frozenset(
    {"/health", "/ready", "/v1/messages/health", "/metrics", "/v1/daari/stats"}
)


class BodyTooLarge(Exception):
    """Raised when a streamed body exceeds the configured cap mid-read."""

    def __init__(self, *, limit: int, received: int) -> None:
        self.limit = limit
        self.received = received
        super().__init__(f"body exceeds {limit} bytes")


def body_limit_for_path(path: str, *, max_body_bytes: int, files_max_total: int) -> int:
    """Per-route override: uploads may exceed the general chat/JSON cap."""
    base = max(0, int(max_body_bytes))
    if path.startswith("/v1/files") or path.startswith("/v1/audio/") or path.startswith(
        "/v1/images/edits"
    ):
        floor = max(UPLOAD_ROUTE_FLOOR_BYTES, int(files_max_total or 0))
        return max(base, floor)
    return base


def is_anthropic_path(path: str) -> bool:
    return path == "/v1/messages" or path.startswith("/v1/messages/")


def body_too_large_response(*, path: str, limit: int, content_length: int | None) -> JSONResponse:
    message = (
        f"Request body exceeds server.max_body_bytes ({limit} bytes)."
        if content_length is None
        else (
            f"Content-Length {content_length} exceeds server.max_body_bytes "
            f"({limit} bytes)."
        )
    )
    if is_anthropic_path(path):
        return JSONResponse(
            status_code=413,
            content={
                "type": "error",
                "error": {
                    "type": "invalid_request_error",
                    "message": message,
                },
            },
        )
    return JSONResponse(
        status_code=413,
        content={
            "error": {
                "message": message,
                "type": "invalid_request_error",
                "code": "request_too_large",
                "max_body_bytes": limit,
            }
        },
    )


def record_body_reject(app: Any, *, path: str, limit: int, content_length: int | None) -> None:
    metrics = getattr(getattr(app.state, "ctx", None), "metrics", None)
    if metrics is not None and hasattr(metrics, "record_reject"):
        metrics.record_reject("body_too_large")
    log_gateway_event(
        "body_too_large",
        {
            "path": path,
            "max_body_bytes": limit,
            "content_length": content_length,
        },
    )


class BodySizeLimitMiddleware:
    """ASGI middleware: Content-Length check + capped streamed reads."""

    def __init__(
        self,
        app: ASGIApp,
        *,
        max_body_bytes: int = DEFAULT_MAX_BODY_BYTES,
        files_max_total_bytes: int = 0,
    ) -> None:
        self.app = app
        self.max_body_bytes = max(0, int(max_body_bytes))
        self.files_max_total_bytes = max(0, int(files_max_total_bytes))

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        method = scope.get("method", "GET").upper()
        if method in {"GET", "HEAD", "OPTIONS", "TRACE"}:
            await self.app(scope, receive, send)
            return
        path = scope.get("path") or ""
        if path in OPEN_BODY_PATHS:
            await self.app(scope, receive, send)
            return
        if self.max_body_bytes <= 0:
            await self.app(scope, receive, send)
            return

        limit = body_limit_for_path(
            path,
            max_body_bytes=self.max_body_bytes,
            files_max_total=self.files_max_total_bytes,
        )
        if limit <= 0:
            await self.app(scope, receive, send)
            return

        content_length: int | None = None
        for key, value in scope.get("headers") or []:
            if key.lower() == b"content-length":
                try:
                    content_length = int(value.decode("latin-1"))
                except (ValueError, UnicodeDecodeError):
                    content_length = None
                break

        # Build a tiny FastAPI Request only for error shaping / metrics access
        # via the inner app's state — we need the FastAPI app instance.
        if content_length is not None and content_length > limit:
            # Deferred: we need app.state from the inner FastAPI app. Call into
            # a response helper after wrapping; for Content-Length we short-circuit
            # by running a minimal path through Request against self.app.
            await self._reject(scope, receive, send, path=path, limit=limit, content_length=content_length)
            return

        received = 0

        async def limited_receive() -> dict:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                chunk = message.get("body", b"") or b""
                received += len(chunk)
                if received > limit:
                    raise BodyTooLarge(limit=limit, received=received)
            return message

        try:
            await self.app(scope, limited_receive, send)
        except BodyTooLarge:
            await self._reject(
                scope, receive, send, path=path, limit=limit, content_length=content_length
            )

    async def _reject(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
        *,
        path: str,
        limit: int,
        content_length: int | None,
    ) -> None:
        # Reach FastAPI app.state by constructing Request after a no-op probe is
        # awkward; instead walk the middleware stack: the FastAPI app is
        # `self.app` only when no other middleware wraps it. Prefer reading
        # from scope["app"] which Starlette sets.
        app = scope.get("app")
        if app is not None:
            record_body_reject(app, path=path, limit=limit, content_length=content_length)
        else:
            log_gateway_event(
                "body_too_large",
                {
                    "path": path,
                    "max_body_bytes": limit,
                    "content_length": content_length,
                },
            )
        response = body_too_large_response(
            path=path, limit=limit, content_length=content_length
        )
        await response(scope, receive, send)


def install_body_size_limit(app: Any, settings: Any) -> None:
    """Register the body-size middleware outermost so it runs before body buffering."""
    max_body = int(getattr(getattr(settings, "server", None), "max_body_bytes", DEFAULT_MAX_BODY_BYTES) or 0)
    files_cap = int(getattr(getattr(settings, "files", None), "max_total_bytes", 0) or 0)
    if max_body <= 0:
        return
    app.add_middleware(
        BodySizeLimitMiddleware,
        max_body_bytes=max_body,
        files_max_total_bytes=files_cap,
    )
