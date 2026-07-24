"""Live-source providers: Open-Meteo, wttr.in, generic REST (issue #120).

Triggered by @weather / weather-like prompts or @source:<id>. Priority and
endpoints come from ~/.daari/sources.yaml (see load_sources_config).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx
import yaml

from daari.gateway.internal import DaariMeta, InternalRequest, InternalResponse
from daari.providers.integrations import HttpIntegrationProvider

DEFAULT_SOURCES_PATH = Path.home() / ".daari" / "sources.yaml"

DEFAULT_SOURCES = {
    "priority": ["open-meteo", "wttr", "generic"],
    "providers": {
        "open-meteo": {
            "type": "open-meteo",
            "triggers": ["@weather", "@open-meteo"],
        },
        "wttr": {
            "type": "wttr",
            "triggers": ["@wttr"],
        },
        "generic": {
            "type": "generic-rest",
            "triggers": ["@source"],
            # Example: endpoints: [{id: status, url: "https://example.com/health"}]
            "endpoints": [],
        },
    },
}


@dataclass
class SourcesConfig:
    priority: list[str] = field(default_factory=lambda: list(DEFAULT_SOURCES["priority"]))
    providers: dict[str, dict[str, Any]] = field(default_factory=dict)
    path: str = ""


def load_sources_config(path: str | Path | None = None) -> SourcesConfig:
    target = Path(path).expanduser() if path else DEFAULT_SOURCES_PATH
    if not target.is_file():
        return SourcesConfig(providers=dict(DEFAULT_SOURCES["providers"]), path=str(target))
    try:
        loaded = yaml.safe_load(target.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return SourcesConfig(providers=dict(DEFAULT_SOURCES["providers"]), path=str(target))
    if not isinstance(loaded, dict):
        return SourcesConfig(providers=dict(DEFAULT_SOURCES["providers"]), path=str(target))
    priority = loaded.get("priority") or DEFAULT_SOURCES["priority"]
    providers = loaded.get("providers") or DEFAULT_SOURCES["providers"]
    if not isinstance(priority, list):
        priority = list(DEFAULT_SOURCES["priority"])
    if not isinstance(providers, dict):
        providers = dict(DEFAULT_SOURCES["providers"])
    return SourcesConfig(priority=[str(p) for p in priority], providers=providers, path=str(target))


_CITY_RE = re.compile(
    r"(?i)\b(?:weather|forecast|temperature)\b(?:\s+(?:in|for|at))?\s+([A-Za-z][A-Za-z .'-]{1,60})"
)


def extract_location(text: str) -> str:
    cleaned = re.sub(r"(?i)^@(weather|open-meteo|wttr)\s*", "", text.strip())
    match = _CITY_RE.search(cleaned)
    if match:
        return match.group(1).strip(" ?.!")
    # Bare "@weather Paris" or "Paris weather"
    tokens = cleaned.split()
    if tokens:
        return tokens[-1].strip(" ?.!")
    return "London"


class OpenMeteoProvider(HttpIntegrationProvider):
    def __init__(self) -> None:
        super().__init__(id="live:open-meteo", base_url="https://api.open-meteo.com")
        self.token_env_var = ""  # no auth

    async def health(self) -> bool:
        return True

    async def execute(self, request: InternalRequest) -> InternalResponse:
        text = next((m.content or "" for m in reversed(request.messages) if m.role == "user"), "")
        location = extract_location(text)
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                geo = await client.get(
                    "https://geocoding-api.open-meteo.com/v1/search",
                    params={"name": location, "count": 1},
                )
                geo.raise_for_status()
                results = (geo.json() or {}).get("results") or []
                if not results:
                    return self._ok_response(
                        request, self.id, f"Open-Meteo: no geocode result for {location!r}."
                    )
                place = results[0]
                lat, lon = place["latitude"], place["longitude"]
                name = place.get("name", location)
                weather = await client.get(
                    f"{self.base_url}/v1/forecast",
                    params={
                        "latitude": lat,
                        "longitude": lon,
                        "current": "temperature_2m,relative_humidity_2m,weather_code",
                    },
                )
                weather.raise_for_status()
                current = (weather.json() or {}).get("current") or {}
                temp = current.get("temperature_2m")
                humidity = current.get("relative_humidity_2m")
                content = (
                    f"Weather in {name}: {temp}°C, humidity {humidity}% "
                    f"(Open-Meteo; weather_code={current.get('weather_code')})."
                )
                return self._ok_response(request, self.id, content)
        except Exception as exc:  # noqa: BLE001
            return self._failure(request, exc)


class WttrProvider(HttpIntegrationProvider):
    def __init__(self) -> None:
        super().__init__(id="live:wttr", base_url="https://wttr.in")
        self.token_env_var = ""

    async def health(self) -> bool:
        return True

    async def execute(self, request: InternalRequest) -> InternalResponse:
        text = next((m.content or "" for m in reversed(request.messages) if m.role == "user"), "")
        location = extract_location(text)
        url = f"{self.base_url}/{quote(location)}?format=3"
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.get(url, headers={"User-Agent": "daari"})
                response.raise_for_status()
                return self._ok_response(request, self.id, response.text.strip())
        except Exception as exc:  # noqa: BLE001
            return self._failure(request, exc)


class GenericRestProvider(HttpIntegrationProvider):
    def __init__(self, endpoints: list[dict[str, Any]] | None = None) -> None:
        super().__init__(id="live:generic", base_url="")
        self.token_env_var = ""
        self.endpoints = endpoints or []

    async def health(self) -> bool:
        return True

    async def execute(self, request: InternalRequest) -> InternalResponse:
        text = next((m.content or "" for m in reversed(request.messages) if m.role == "user"), "")
        # "@source status" → endpoint id "status"
        match = re.match(r"(?i)^@source(?:\s+|:)(\S+)", text.strip())
        endpoint_id = match.group(1) if match else None
        endpoint = None
        for entry in self.endpoints:
            if endpoint_id and entry.get("id") == endpoint_id:
                endpoint = entry
                break
        if endpoint is None and self.endpoints:
            endpoint = self.endpoints[0]
        if not endpoint or not endpoint.get("url"):
            return InternalResponse(
                content="No generic REST endpoints configured in sources.yaml.",
                model=request.model,
                daari_meta=DaariMeta(
                    tier="Lt",
                    executor="integration",
                    provider_id=self.id,
                    task_type="tool",
                    warning="sources_unconfigured",
                ),
            )
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.get(str(endpoint["url"]))
                response.raise_for_status()
                body = response.text[:2000]
                return self._ok_response(
                    request, self.id, f"{endpoint.get('id', 'endpoint')}: {body}"
                )
        except Exception as exc:  # noqa: BLE001
            return self._failure(request, exc)


def build_live_providers(
    config: SourcesConfig | None = None,
) -> list[HttpIntegrationProvider]:
    cfg = config or load_sources_config()
    built: dict[str, HttpIntegrationProvider] = {
        "open-meteo": OpenMeteoProvider(),
        "wttr": WttrProvider(),
        "generic": GenericRestProvider(
            endpoints=list((cfg.providers.get("generic") or {}).get("endpoints") or [])
        ),
    }
    ordered: list[HttpIntegrationProvider] = []
    for name in cfg.priority:
        if name in built:
            ordered.append(built.pop(name))
    ordered.extend(built.values())
    return ordered


def live_triggers(config: SourcesConfig | None = None) -> dict[str, list[str]]:
    """provider_id -> trigger list for Router.integration_triggers."""
    cfg = config or load_sources_config()
    mapping = {
        "open-meteo": "live:open-meteo",
        "wttr": "live:wttr",
        "generic": "live:generic",
    }
    triggers: dict[str, list[str]] = {}
    for name, provider_id in mapping.items():
        entry = cfg.providers.get(name) or {}
        listed = entry.get("triggers") or DEFAULT_SOURCES["providers"].get(name, {}).get(
            "triggers", []
        )
        triggers[provider_id] = [str(t) for t in listed]
    # Also route bare "weather" phrases to the highest-priority weather provider.
    weather_provider = next(
        (mapping[n] for n in cfg.priority if n in {"open-meteo", "wttr"}),
        "live:open-meteo",
    )
    triggers.setdefault(weather_provider, [])
    if "@weather" not in triggers[weather_provider]:
        triggers[weather_provider] = ["@weather", *triggers[weather_provider]]
    return triggers
