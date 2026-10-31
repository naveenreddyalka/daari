"""Named virtual models → ordered local/L6 candidate lists (#2023)."""

from __future__ import annotations

from typing import Any, Literal

Kind = Literal["local", "frontier"]


def resolve_virtual_candidates(
    model: str | None,
    virtual_models: dict[str, list[str]] | None,
) -> list[str] | None:
    """Return the ordered candidate list when ``model`` is a configured virtual name."""
    name = (model or "").strip()
    if not name or not virtual_models:
        return None
    candidates = virtual_models.get(name)
    if not candidates:
        return None
    cleaned = [str(c).strip() for c in candidates if str(c).strip()]
    return cleaned or None


def classify_candidate(candidate: str, settings: Any) -> tuple[Kind, str]:
    """Map a candidate id to (``local``, tier) or (``frontier``, model_id)."""
    raw = (candidate or "").strip()
    upper = raw.upper()
    if upper in {"L3", "L4", "L5"}:
        return "local", upper
    if upper in {"L6", "FRONTIER"}:
        return "frontier", "L6"

    if settings is None:
        return "frontier", raw

    models = getattr(settings, "models", None)
    for tier, attr in (("L3", "l3"), ("L4", "l4"), ("L5", "l5")):
        configured = getattr(models, attr, None) if models is not None else None
        if configured and raw == configured:
            return "local", tier

    pool = getattr(getattr(settings, "routing", None), "local_pool", None)
    for backend in getattr(pool, "backends", None) or []:
        if getattr(backend, "model", "") == raw:
            tiers = [t.upper() for t in (getattr(backend, "tiers", None) or [])]
            for tier in ("L3", "L4", "L5"):
                if tier in tiers:
                    return "local", tier
            return "local", "L3"

    return "frontier", raw


def known_local_ids(settings: Any) -> set[str]:
    """Configured local model / tier ids doctor treats as known."""
    known = {"L3", "L4", "L5", "L6", "FRONTIER", "l3", "l4", "l5", "l6", "frontier"}
    if settings is None:
        return known
    models = getattr(settings, "models", None)
    for attr in ("l3", "l4", "l5"):
        value = getattr(models, attr, None) if models is not None else None
        if value:
            known.add(str(value))
    pool = getattr(getattr(settings, "routing", None), "local_pool", None)
    for backend in getattr(pool, "backends", None) or []:
        model = getattr(backend, "model", "") or ""
        if model:
            known.add(model)
        bid = getattr(backend, "id", "") or ""
        if bid:
            known.add(bid)
    frontier = getattr(settings, "frontier", None)
    default = getattr(frontier, "default_model", None) if frontier is not None else None
    if default:
        known.add(str(default))
    return known


def virtual_models_findings(settings: Any) -> list[str]:
    """Doctor findings for empty lists / unknown-looking candidate ids."""
    if settings is None:
        return []
    routing = getattr(settings, "routing", None)
    mapping = getattr(routing, "virtual_models", None) or {}
    if not mapping:
        return []
    known = known_local_ids(settings)
    findings: list[str] = []
    for name, candidates in mapping.items():
        cleaned = [str(c).strip() for c in (candidates or []) if str(c).strip()]
        if not cleaned:
            findings.append(f"routing.virtual_models[{name!r}] has an empty candidate list")
            continue
        for candidate in cleaned:
            if candidate in known:
                continue
            if "/" in candidate:
                # Provider-style frontier id (openai/gpt-4o-mini, openrouter/…).
                continue
            if candidate.upper() in {"L3", "L4", "L5", "L6", "FRONTIER"}:
                continue
            findings.append(
                f"routing.virtual_models[{name!r}] candidate {candidate!r} looks unknown "
                "(not a local tier, configured models.* id, or provider/model frontier id)"
            )
    return findings
