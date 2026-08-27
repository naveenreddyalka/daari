"""Detect OpenRouter-style failover reasons on local backends (G5 / #244)."""

from __future__ import annotations

_CONTEXT_NEEDLES = (
    "context length",
    "context window",
    "maximum context",
    "exceeds the context",
    "prompt is too long",
    "too long for the model",
    "num_ctx",
)


def is_context_length_error(exc: BaseException) -> bool:
    text = str(exc).lower()
    return any(needle in text for needle in _CONTEXT_NEEDLES)
