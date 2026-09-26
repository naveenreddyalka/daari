"""Per-key and per-team model allowlists (#708).

Patterns are exact names or globs (`claude-*`). A key allowlist intersects
the team allowlist: the key may only narrow what the team already permits.
Either side left unset means that side does not restrict.
"""

from __future__ import annotations

import fnmatch
import json
from typing import Any


class ModelAccessDenied(Exception):
    """Requested model is outside the key/team allowlist."""

    def __init__(self, model: str) -> None:
        self.model = model
        super().__init__(model)


def coerce_names(raw: list[str] | tuple[str, ...] | None) -> tuple[str, ...] | None:
    """None stays unrestricted. A list (even empty) is an explicit allowlist."""
    if raw is None:
        return None
    return tuple(str(item).strip() for item in raw if str(item).strip())


def encode_names(values: tuple[str, ...] | list[str] | None) -> str | None:
    if values is None:
        return None
    return json.dumps([str(item) for item in values])


def decode_names(raw: Any) -> tuple[str, ...] | None:
    """NULL / missing → unrestricted. A JSON list (even `[]`) is explicit."""
    if raw is None:
        return None
    if isinstance(raw, (list, tuple)):
        return tuple(str(item).strip() for item in raw if str(item).strip())
    if not isinstance(raw, str) or not raw.strip():
        return None
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if payload is None:
        return None
    if not isinstance(payload, list):
        return None
    return tuple(str(item).strip() for item in payload if str(item).strip())


def effective_patterns(
    allowed_models: list[str] | tuple[str, ...] | None,
    model_groups: list[str] | tuple[str, ...] | None,
    catalog: dict[str, list[str]] | None,
) -> list[str] | None:
    """Union of explicit patterns and named groups. None if both unset.

    An unknown group contributes nothing. If the only input is a missing
    group, the result is an empty list (fail closed).
    """
    if allowed_models is None and model_groups is None:
        return None
    patterns: list[str] = []
    if allowed_models is not None:
        patterns.extend(str(item).strip() for item in allowed_models if str(item).strip())
    if model_groups is not None:
        groups = catalog or {}
        for name in model_groups:
            members = groups.get(str(name)) or []
            if isinstance(members, str):
                members = [members]
            patterns.extend(str(item).strip() for item in members if str(item).strip())
    return patterns


def pattern_matches(model: str, pattern: str) -> bool:
    name = (model or "").strip()
    expr = (pattern or "").strip()
    if not name or not expr:
        return False
    return fnmatch.fnmatchcase(name, expr)


def groups_for_model(
    model: str,
    catalog: dict[str, list[str]] | None,
) -> tuple[str, ...]:
    """Catalog group names whose patterns match ``model`` (#1109)."""
    if not catalog:
        return ()
    name = (model or "").strip()
    if not name:
        return ()
    matched: list[str] = []
    for group_name, members in catalog.items():
        patterns = [members] if isinstance(members, str) else list(members or [])
        if any(pattern_matches(name, str(p)) for p in patterns if str(p).strip()):
            matched.append(str(group_name))
    return tuple(matched)


def model_permitted(
    model: str,
    *,
    key_patterns: list[str] | tuple[str, ...] | None,
    team_patterns: list[str] | tuple[str, ...] | None,
) -> bool:
    """True when both sides that are set match. Unset side does not restrict."""
    if team_patterns is not None and not any(
        pattern_matches(model, pattern) for pattern in team_patterns
    ):
        return False
    if key_patterns is not None and not any(
        pattern_matches(model, pattern) for pattern in key_patterns
    ):
        return False
    return True


def patterns_from_claims(
    claims: Any,
    catalog: dict[str, list[str]] | None,
) -> tuple[list[str] | None, list[str] | None]:
    """Return (key_patterns, team_patterns). Master / missing claims → unrestricted."""
    if claims is None or getattr(claims, "kind", None) != "virtual":
        return None, None
    key = getattr(claims, "virtual_key", None)
    allowed = getattr(claims, "allowed_models", None)
    groups = getattr(claims, "model_groups", None)
    if key is not None:
        if allowed is None:
            allowed = getattr(key, "allowed_models", None)
        if groups is None:
            groups = getattr(key, "model_groups", None)
    return (
        effective_patterns(allowed, groups, catalog),
        effective_patterns(
            getattr(claims, "team_allowed_models", None),
            getattr(claims, "team_model_groups", None),
            catalog,
        ),
    )


def frontier_models_permitted(
    frontier: Any,
    *,
    key_patterns: list[str] | tuple[str, ...] | None,
    team_patterns: list[str] | tuple[str, ...] | None,
) -> bool:
    """False when an allowlist is set and no frontier slot model matches it."""
    if key_patterns is None and team_patterns is None:
        return True
    if frontier is None:
        return False
    models: list[str] = []
    slots = getattr(frontier, "slots", None)
    if slots:
        for slot in slots:
            executor = getattr(slot, "executor", None)
            models.append(getattr(executor, "default_model", "") or "")
    else:
        models.append(getattr(frontier, "default_model", "") or "")
    return any(
        model_permitted(model, key_patterns=key_patterns, team_patterns=team_patterns)
        for model in models
        if model
    )


def denial_body(model: str) -> dict[str, Any]:
    """403 payload. Model name only — never a key, hash, or other secret."""
    name = (model or "").strip()
    return {
        "error": {
            "type": "model_not_allowed",
            "code": "model_not_allowed",
            "message": f"Model not allowed for this key: {name}",
        }
    }


def record_model_denial(
    settings: Any,
    *,
    model: str,
    key_id: str | None,
    client_id: str | None,
    path: str,
) -> None:
    from daari.enterprise.postgres_audit import audit_log_from_settings

    audit_log_from_settings(settings).record(
        actor=client_id or key_id or "virtual",
        role="key",
        action="auth.model_denied",
        detail={
            "model": (model or "").strip(),
            "key_id": key_id,
            "path": path,
        },
    )
