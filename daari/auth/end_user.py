"""End-user id attribution from OpenAI and Anthropic request bodies (#1933)."""

from __future__ import annotations

from typing import Any


def end_user_from_payload(payload: Any) -> str:
    """Named end user for per-user fences.

    OpenAI top-level ``user`` wins when present and non-empty. Otherwise
    Anthropic ``metadata.user_id`` is used. Empty string when neither is set.
    """
    if not isinstance(payload, dict):
        return ""
    top = payload.get("user")
    if top is not None:
        named = str(top).strip()
        if named:
            return named
    return end_user_from_metadata(payload.get("metadata"))


def end_user_from_metadata(metadata: Any) -> str:
    """Anthropic ``metadata.user_id`` (dict or object); empty when absent."""
    if metadata is None:
        return ""
    if isinstance(metadata, dict):
        uid = metadata.get("user_id")
    else:
        uid = getattr(metadata, "user_id", None)
    if uid is None:
        return ""
    return str(uid).strip()
