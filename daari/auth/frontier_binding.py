"""Per-team / per-key frontier credential binding (team BYOK, #2216).

Opt-in: unbound tenants keep the global frontier key. Bound tenants sign L6
with their own credential (plain or ``secret://``) or pin a named pool slot.
"""

from __future__ import annotations

from typing import Any

from daari.security.secret_refs import REDACTED, SecretRefError, is_secret_ref, resolve_secret_ref

_UNSET = object()


class FrontierBindingError(RuntimeError):
    """Bound frontier credential missing, empty, or unresolvable — fail closed."""

    def __init__(self, message: str, *, status_code: int = 502) -> None:
        super().__init__(message)
        self.status_code = status_code


def coerce_binding_value(raw: Any) -> str | None:
    """None clears; non-empty stripped string keeps; blank raises."""
    if raw is None:
        return None
    if not isinstance(raw, str):
        raise ValueError("frontier_api_key must be a string or null")
    text = raw.strip()
    if not text:
        raise ValueError("frontier_api_key must be non-empty when set")
    return text


def coerce_pool_name(raw: Any) -> str | None:
    if raw is None:
        return None
    if not isinstance(raw, str):
        raise ValueError("frontier_pool must be a string or null")
    text = raw.strip()
    if not text:
        raise ValueError("frontier_pool must be non-empty when set")
    return text


def binding_from_meta(metadata: dict[str, Any] | None) -> tuple[str | None, str | None]:
    if not isinstance(metadata, dict):
        return None, None
    key = metadata.get("frontier_api_key")
    pool = metadata.get("frontier_pool")
    key_out = str(key).strip() if isinstance(key, str) and str(key).strip() else None
    pool_out = str(pool).strip() if isinstance(pool, str) and str(pool).strip() else None
    return key_out, pool_out


def write_binding_to_meta(
    metadata: dict[str, Any],
    *,
    frontier_api_key: str | None | object = _UNSET,
    frontier_pool: str | None | object = _UNSET,
    unset_sentinel: object | None = None,
) -> dict[str, Any]:
    """Mutate and return metadata. Pass ``unset_sentinel`` / ``_UNSET`` to leave a side alone."""
    meta = dict(metadata)
    sentinel = _UNSET if unset_sentinel is None else unset_sentinel
    if frontier_api_key is not sentinel:
        value = coerce_binding_value(frontier_api_key)
        if value is None:
            meta.pop("frontier_api_key", None)
        else:
            meta["frontier_api_key"] = value
    if frontier_pool is not sentinel:
        pool = coerce_pool_name(frontier_pool)
        if pool is None:
            meta.pop("frontier_pool", None)
        else:
            meta["frontier_pool"] = pool
    return meta


def redact_binding_value(raw: str | None) -> str | None:
    """Admin reads never echo the credential — only a redaction marker when bound."""
    if raw is None or not str(raw).strip():
        return None
    return REDACTED


def resolve_bound_key(raw: str | None) -> str:
    """Resolve a binding to the upstream credential. Fail closed on empty/ref errors."""
    if raw is None or not str(raw).strip():
        raise FrontierBindingError("frontier binding is empty", status_code=502)
    text = str(raw).strip()
    try:
        if is_secret_ref(text):
            value = resolve_secret_ref(text)
        else:
            value = text
    except SecretRefError as exc:
        raise FrontierBindingError(
            f"frontier binding unresolvable: {exc}", status_code=502
        ) from exc
    if not value or not str(value).strip():
        raise FrontierBindingError("frontier binding resolved empty", status_code=502)
    return str(value).strip()


def effective_binding(
    *,
    key_api_key: str | None = None,
    key_pool: str | None = None,
    team_api_key: str | None = None,
    team_pool: str | None = None,
) -> tuple[str | None, str | None]:
    """Key binding wins over team; either side may supply only a pool pin."""
    api_key = key_api_key or team_api_key
    pool = key_pool or team_pool
    return api_key, pool


def binding_source(key_value: str | None, team_value: str | None) -> str | None:
    """Which layer supplied one side of the effective binding (same precedence)."""
    if key_value:
        return "key"
    if team_value:
        return "team"
    return None


def record_frontier_binding(metrics: Any, *, outcome: str, source: str | None) -> None:
    """Count a binding outcome where the binding is consumed (#2316).

    No-op without a Metrics sink so pool/door code paths never fail on
    observability. Global-key traffic must not call this.
    """
    if metrics is None or not hasattr(metrics, "record_frontier_binding"):
        return
    metrics.record_frontier_binding(outcome=outcome, source=source)
CREDENTIAL_SOURCE_GLOBAL = "global"
CREDENTIAL_SOURCE_TEAM = "team"
CREDENTIAL_SOURCE_KEY = "key"


def binding_credential_source(
    *,
    key_api_key: str | None = None,
    team_api_key: str | None = None,
) -> str | None:
    """Which credential signs L6 for this binding (#2314); None when unbound.

    Mirrors ``effective_binding`` precedence: key over team. A pool pin alone
    still signs with the slot's shared (global) key, so it is not a source.
    """
    if key_api_key:
        return CREDENTIAL_SOURCE_KEY
    if team_api_key:
        return CREDENTIAL_SOURCE_TEAM
    return None


def credential_source_for_meta(meta: Any) -> str:
    """``global`` | ``team`` | ``key`` for the request about to hit L6 (#2314).

    A bound ``frontier_api_key`` without a recorded origin is attributed to the
    key, the most specific scope that can set it directly.
    """
    explicit = getattr(meta, "frontier_credential_source", None)
    if isinstance(explicit, str) and explicit.strip():
        return explicit.strip()
    if getattr(meta, "frontier_api_key", None):
        return CREDENTIAL_SOURCE_KEY
    return CREDENTIAL_SOURCE_GLOBAL
