"""Per-key and per-team service_tier / Anthropic speed allowlists (#2070).

Unset allowlists (both sides None) keep unrestricted behavior. When both key
and team set a list, the effective allowlist is the **intersection** (most
restrictive), matching model allowlists and budget merge precedent.
"""

from __future__ import annotations

from typing import Any, Iterable

from daari.auth.model_access import coerce_names


def normalize_tier_name(raw: str | None) -> str | None:
    if raw is None:
        return None
    text = str(raw).strip().lower()
    return text or None


def coerce_tiers(raw: list[str] | tuple[str, ...] | None) -> tuple[str, ...] | None:
    """None stays unrestricted. A list (even empty) is an explicit allowlist."""
    names = coerce_names(raw)
    if names is None:
        return None
    return tuple(normalize_tier_name(item) or item for item in names if normalize_tier_name(item))


def tiers_from_meta(metadata: dict[str, Any] | None) -> tuple[str, ...] | None:
    if not isinstance(metadata, dict):
        return None
    if "allowed_service_tiers" not in metadata:
        return None
    raw = metadata.get("allowed_service_tiers")
    if raw is None:
        return None
    if isinstance(raw, (list, tuple)):
        return coerce_tiers(list(raw))
    return None


def degrade_from_meta(metadata: dict[str, Any] | None) -> bool:
    if not isinstance(metadata, dict):
        return False
    return bool(metadata.get("degrade_disallowed_service_tier"))


def write_tiers_to_meta(
    metadata: dict[str, Any],
    *,
    allowed_service_tiers: list[str] | tuple[str, ...] | None | object = None,
    degrade_disallowed_service_tier: bool | None = None,
    unset_sentinel: object | None = None,
) -> dict[str, Any]:
    """Mutate and return metadata. Pass ``unset_sentinel`` to leave a side alone."""
    meta = dict(metadata)
    if allowed_service_tiers is not unset_sentinel:
        tiers = coerce_tiers(allowed_service_tiers)  # type: ignore[arg-type]
        if tiers is None:
            meta.pop("allowed_service_tiers", None)
        else:
            meta["allowed_service_tiers"] = list(tiers)
    if degrade_disallowed_service_tier is not None:
        if degrade_disallowed_service_tier:
            meta["degrade_disallowed_service_tier"] = True
        else:
            meta.pop("degrade_disallowed_service_tier", None)
    return meta


def effective_allowed_service_tiers(
    key_tiers: Iterable[str] | None,
    team_tiers: Iterable[str] | None,
) -> tuple[str, ...] | None:
    """Intersect key and team allowlists. None on either side means no restrict."""
    key = coerce_tiers(list(key_tiers) if key_tiers is not None else None)
    team = coerce_tiers(list(team_tiers) if team_tiers is not None else None)
    if key is None and team is None:
        return None
    if key is None:
        return team
    if team is None:
        return key
    team_set = set(team)
    return tuple(item for item in key if item in team_set)


def service_tier_permitted(
    requested: str | None,
    *,
    allowed: Iterable[str] | None,
) -> bool:
    """True when unset request, unset allowlist, or requested name is listed."""
    name = normalize_tier_name(requested)
    if not name:
        return True
    if allowed is None:
        return True
    allowed_set = {normalize_tier_name(item) for item in allowed}
    allowed_set.discard(None)
    return name in allowed_set


def effective_degrade(
    key_degrade: bool = False,
    team_degrade: bool = False,
) -> bool:
    """Opt-in degrade if either key or team enables it."""
    return bool(key_degrade or team_degrade)


def denial_body(*, requested: str, field: str = "service_tier") -> dict[str, Any]:
    name = normalize_tier_name(requested) or str(requested or "")
    label = "speed" if field == "speed" else "service_tier"
    return {
        "error": {
            "type": "service_tier_not_allowed",
            "code": "service_tier_not_allowed",
            "message": f"{label} '{name}' is not permitted for this key.",
            label: name,
        }
    }
