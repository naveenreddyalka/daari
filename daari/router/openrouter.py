"""First-class OpenRouter L6 slot (G3 / #225)."""

from __future__ import annotations

from daari.config.settings import FrontierProviderConfig
from daari.gateway.provider_prefs import is_openrouter_base, normalize_region

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
OPENROUTER_REFERER = "https://github.com/naveenreddyalka/daari"
OPENROUTER_TITLE = "daari"

# OpenRouter in-region routing is hostname-based (#1052).
_OPENROUTER_REGIONAL = {
    "us": "https://us.openrouter.ai/api/v1",
    "eu": "https://eu.openrouter.ai/api/v1",
}


def openrouter_slot(
    *,
    model: str = "openrouter/auto",
    zdr: bool = False,
    region: str = "",
) -> FrontierProviderConfig:
    """Documented default slot. BYOK via OPENROUTER_API_KEY."""
    return FrontierProviderConfig(
        id="openrouter",
        base_url=OPENROUTER_BASE_URL,
        model=model,
        api_key_env="OPENROUTER_API_KEY",
        zdr=zdr,
        region=region,
    )


def openrouter_headers(api_key: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {api_key}",
        "HTTP-Referer": OPENROUTER_REFERER,
        "X-Title": OPENROUTER_TITLE,
    }


def openrouter_base_for_region(region_pin: str | None, current_base: str) -> str:
    """Rewrite OpenRouter bases to us/eu regional hosts when pinned (#1052).

    Non-OpenRouter URLs and unpinned / non-us-eu pins are returned unchanged.
    """
    pin = normalize_region(region_pin)
    if pin not in _OPENROUTER_REGIONAL or not is_openrouter_base(current_base):
        return current_base
    return _OPENROUTER_REGIONAL[pin]


def openrouter_can_satisfy_region(region_pin: str | None, base_url: str) -> bool:
    """True when an OpenRouter slot can honor us/eu residency via host rewrite."""
    pin = normalize_region(region_pin)
    return pin in _OPENROUTER_REGIONAL and is_openrouter_base(base_url)


def live_openrouter_available() -> bool:
    import os

    return bool(os.environ.get("OPENROUTER_API_KEY"))
