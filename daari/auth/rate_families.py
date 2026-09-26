"""Modality-family rate limits on virtual keys (#1099).

Per-key ``metadata.rate_families`` maps a family name to optional ``rpm`` /
``tpm`` ceilings. Counters are keyed by ``{key_id}:{family}`` so exhausting
images does not starve chat (and vice versa). Unset families keep today's
global key rpm/tpm behavior only.
"""

from __future__ import annotations

from typing import Any

# Stable family names used in counter keys and docs.
RATE_FAMILIES = frozenset(
    {"chat", "embeddings", "images", "audio", "moderations", "rerank", "other"}
)


def rate_limit_family(path: str) -> str:
    """Map a request path to a modality family."""
    p = (path or "").split("?", 1)[0]
    if p == "/v1/moderations" or p.startswith("/v1/moderations/") or p == "/v1/messages/moderations":
        return "moderations"
    if p.startswith("/v1/chat/") or p in {"/v1/responses", "/v1/messages"} or p.startswith(
        "/v1/messages/"
    ):
        return "chat"
    if p.startswith("/v1/embeddings") or p in {"/api/embed", "/api/embeddings"}:
        return "embeddings"
    if p.startswith("/v1/images/"):
        return "images"
    if p.startswith("/v1/audio/"):
        return "audio"
    if p.startswith("/v1/rerank"):
        return "rerank"
    return "other"


def family_limits_from_key(key: Any | None, family: str) -> tuple[int, int]:
    """Return ``(rpm, tpm)`` for ``family`` from key metadata (0 = unset)."""
    if key is None:
        return 0, 0
    meta = getattr(key, "metadata", None) or {}
    raw = meta.get("rate_families")
    if not isinstance(raw, dict):
        return 0, 0
    entry = raw.get(family)
    if not isinstance(entry, dict):
        return 0, 0
    try:
        rpm = max(0, int(entry.get("rpm") or 0))
    except (TypeError, ValueError):
        rpm = 0
    try:
        tpm = max(0, int(entry.get("tpm") or 0))
    except (TypeError, ValueError):
        tpm = 0
    return rpm, tpm
