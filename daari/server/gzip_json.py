"""Gzip buffered JSON bodies larger than 16 KiB off the event loop (#1710)."""

from __future__ import annotations

import asyncio
import gzip
from typing import Any

GZIP_MIN_BYTES = 16 * 1024
# Cap while waiting for more_body=False so true streaming JSON cannot grow unbounded.
# BaseHTTPMiddleware sends one data chunk with more_body=True plus an empty trailer.
GZIP_MAX_BUFFER_BYTES = 16 * 1024 * 1024


def accepts_gzip(header: str | None) -> bool:
    if not header:
        return False
    for part in header.split(","):
        bits = [bit.strip() for bit in part.strip().split(";") if bit.strip()]
        if not bits:
            continue
        coding = bits[0].lower()
        if coding not in {"gzip", "*"}:
            continue
        quality = 1.0
        for param in bits[1:]:
            if param.lower().startswith("q="):
                try:
                    quality = float(param[2:])
                except ValueError:
                    quality = 0.0
        if quality > 0:
            return True
    return False


def _header_value(raw_headers: list[tuple[bytes, bytes]], name: bytes) -> str:
    name_l = name.lower()
    for key, value in raw_headers:
        if key.lower() == name_l:
            return value.decode("latin-1")
    return ""


def _upsert_header(raw_headers: list[tuple[bytes, bytes]], name: bytes, value: bytes) -> None:
    name_l = name.lower()
    raw_headers[:] = [(key, val) for key, val in raw_headers if key.lower() != name_l]
    raw_headers.append((name, value))


def _is_buffered_json(content_type: str) -> bool:
    base = content_type.split(";", 1)[0].strip().lower()
    if "text/event-stream" in content_type.lower():
        return False
    return base == "application/json" or base.endswith("+json")


def _scope_header(scope: dict, name: bytes) -> str:
    for key, value in scope.get("headers") or []:
        if key.lower() == name:
            return value.decode("latin-1")
    return ""


def _record_gzip(
    scope: dict,
    *,
    result: str,
    reason: str | None = None,
    bytes_before: int = 0,
    bytes_after: int = 0,
) -> None:
    app = scope.get("app")
    metrics = getattr(getattr(getattr(app, "state", None), "ctx", None), "metrics", None)
    if metrics is not None and hasattr(metrics, "record_gzip"):
        metrics.record_gzip(
            result=result,
            reason=reason,
            bytes_before=bytes_before,
            bytes_after=bytes_after,
        )


class GzipJsonMiddleware:
    """Compress buffered ``application/json`` when the client accepts gzip."""

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not accepts_gzip(_scope_header(scope, b"accept-encoding")):
            await self.app(scope, receive, send)
            return

        state: dict[str, Any] = {"mode": "pending", "chunks": []}

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                headers = list(message.get("headers") or [])
                content_type = _header_value(headers, b"content-type")
                already = _header_value(headers, b"content-encoding")
                if already:
                    state["mode"] = "passthrough"
                    _record_gzip(scope, result="skipped", reason="already_encoded")
                    await send(message)
                    return
                if not _is_buffered_json(content_type):
                    state["mode"] = "passthrough"
                    _record_gzip(scope, result="skipped", reason="not_json")
                    await send(message)
                    return
                state["mode"] = "buffer"
                state["start"] = message
                state["headers"] = headers
                return

            if message["type"] != "http.response.body":
                await send(message)
                return

            if state["mode"] == "passthrough":
                await send(message)
                return

            chunk = message.get("body", b"") or b""
            state["chunks"].append(chunk)
            held = b"".join(state["chunks"])
            if message.get("more_body"):
                if len(held) > GZIP_MAX_BUFFER_BYTES:
                    state["mode"] = "passthrough"
                    _record_gzip(scope, result="skipped", reason="streaming")
                    await send(state["start"])
                    await send({"type": "http.response.body", "body": held, "more_body": True})
                return

            body = held
            headers = state["headers"]
            start = state["start"]
            if len(body) > GZIP_MIN_BYTES:
                compressed = await asyncio.to_thread(gzip.compress, body)
                _upsert_header(headers, b"content-encoding", b"gzip")
                vary = _header_value(headers, b"vary")
                if not vary:
                    vary_value = b"Accept-Encoding"
                elif "accept-encoding" not in vary.lower():
                    vary_value = f"{vary}, Accept-Encoding".encode("latin-1")
                else:
                    vary_value = vary.encode("latin-1")
                _upsert_header(headers, b"vary", vary_value)
                _upsert_header(headers, b"content-length", str(len(compressed)).encode())
                _record_gzip(
                    scope,
                    result="compressed",
                    bytes_before=len(body),
                    bytes_after=len(compressed),
                )
                body = compressed
            else:
                _record_gzip(scope, result="skipped", reason="below_min")
            start["headers"] = headers
            await send(start)
            await send({"type": "http.response.body", "body": body, "more_body": False})

        await self.app(scope, receive, send_wrapper)


def install_gzip_json(app: Any) -> None:
    """Register gzip inside the body-limit middleware so request caps stay outermost."""
    app.add_middleware(GzipJsonMiddleware)
