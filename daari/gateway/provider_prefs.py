"""OpenRouter-shaped `provider` object (G2 / #224)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel


class ProviderPreferences(BaseModel):
    """Client routing constraints Cursor already sends to OpenRouter."""

    order: list[str] | None = None
    only: list[str] | None = None
    ignore: list[str] | None = None
    sort: Literal["price", "throughput", "latency"] | None = None
    zdr: bool = False
    data_collection: Literal["allow", "deny"] | None = None
    max_price: dict[str, Any] | None = None
    allow_fallbacks: bool | None = None


class ZdrUnavailable(Exception):
    """`zdr: true` was requested but no L6 slot declares zero-data-retention."""

    def __init__(self) -> None:
        super().__init__(
            "no configured L6 provider declares zdr; refusing to drop the constraint"
        )


def parse_provider(raw: Any) -> ProviderPreferences | None:
    if not raw or not isinstance(raw, dict):
        return None
    prefs = ProviderPreferences.model_validate(raw)
    if prefs.model_dump(exclude_defaults=True) == {}:
        return None
    return prefs


def as_openrouter_payload(prefs: ProviderPreferences) -> dict[str, Any]:
    return prefs.model_dump(exclude_none=True, exclude_defaults=True) | (
        {"zdr": True} if prefs.zdr else {}
    )


def is_openrouter_base(url: str) -> bool:
    return "openrouter.ai" in (url or "").lower()


def configured_frontier_slots(settings: Any) -> list[Any]:
    frontier = settings.frontier
    providers = list(getattr(frontier, "providers", None) or [])
    if providers:
        return providers
    from daari.config.settings import FrontierProviderConfig

    return [
        FrontierProviderConfig(
            id=frontier.provider,
            base_url=frontier.base_url,
            model=frontier.model,
            zdr=False,
        )
    ]


def require_zdr_slot(prefs: ProviderPreferences | None, slots: list[Any]) -> None:
    if prefs is None or not prefs.zdr:
        return
    if not any(bool(getattr(slot, "zdr", False)) for slot in slots):
        raise ZdrUnavailable()


def usage_cost_and_cache(data: dict[str, Any]) -> tuple[float | None, int | None]:
    usage = data.get("usage") if isinstance(data.get("usage"), dict) else {}
    cost_raw = usage.get("cost")
    cost = float(cost_raw) if isinstance(cost_raw, (int, float)) else None
    details = usage.get("prompt_tokens_details")
    details = details if isinstance(details, dict) else {}
    cached_raw = details.get("cached_tokens") or usage.get("cached_tokens")
    cached = int(cached_raw) if isinstance(cached_raw, (int, float)) and cached_raw >= 0 else None
    return cost, cached
