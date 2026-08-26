"""First-class OpenRouter L6 slot (G3 / #225)."""

from __future__ import annotations

from daari.config.settings import FrontierProviderConfig

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
OPENROUTER_REFERER = "https://github.com/naveenreddyalka/daari"
OPENROUTER_TITLE = "daari"


def openrouter_slot(
    *,
    model: str = "openrouter/auto",
    zdr: bool = False,
) -> FrontierProviderConfig:
    """Documented default slot. BYOK via OPENROUTER_API_KEY."""
    return FrontierProviderConfig(
        id="openrouter",
        base_url=OPENROUTER_BASE_URL,
        model=model,
        api_key_env="OPENROUTER_API_KEY",
        zdr=zdr,
    )


def openrouter_headers(api_key: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {api_key}",
        "HTTP-Referer": OPENROUTER_REFERER,
        "X-Title": OPENROUTER_TITLE,
    }


def live_openrouter_available() -> bool:
    import os

    return bool(os.environ.get("OPENROUTER_API_KEY"))
