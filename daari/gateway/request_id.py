"""Inbound X-Request-ID sanitization and resolution (#965, #977)."""

from __future__ import annotations

import contextvars
import re
import uuid
from typing import Any, Mapping

# Cap matches common proxy limits (nginx default custom header practical length).
_MAX_LEN = 128
_PRINTABLE = re.compile(r"^[!-~]+$")

_active_request_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "daari_request_id", default=None
)


def sanitize_request_id(raw: str | None) -> str | None:
    """Return a printable, length-capped id or None if unusable."""
    if raw is None:
        return None
    value = raw.strip()
    if not value or len(value) > _MAX_LEN or not _PRINTABLE.match(value):
        return None
    return value


def resolve_request_id(headers: Mapping[str, Any] | Any) -> str:
    """Prefer inbound X-Request-ID / X-Request-Id; else generate a short hex id.

    ``headers`` is any mapping with case-insensitive ``.get`` (Starlette Headers).
    """
    raw = headers.get("x-request-id") or headers.get("X-Request-ID") or headers.get("X-Request-Id")
    cleaned = sanitize_request_id(raw if isinstance(raw, str) else None)
    if cleaned:
        return cleaned
    return uuid.uuid4().hex[:16]


def bind_request_id(request_id: str | None) -> Any:
    """Bind the active request id for outbound inject (#977)."""
    return _active_request_id.set(request_id or None)


def reset_request_id(token: Any) -> None:
    try:
        _active_request_id.reset(token)
    except Exception:
        pass


def current_request_id() -> str | None:
    return _active_request_id.get()
