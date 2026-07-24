"""F5 live-source providers: Open-Meteo, wttr.in, generic REST (#120)."""

from __future__ import annotations

import httpx
import pytest
import yaml

from daari.gateway.internal import InternalRequest, Message
from daari.providers.live_sources import (
    GenericRestProvider,
    OpenMeteoProvider,
    WttrProvider,
    extract_location,
    live_triggers,
    load_sources_config,
)
from daari.router.router import Router
from daari.cache.exact import ExactCache
from daari.cache.semantic import SemanticCache
from daari.observability.metrics import Metrics
from daari.providers.registry import ProviderRegistry
from daari.router.router import OllamaExecutor
from tests.conftest import NoopEmbedder


def _req(text: str) -> InternalRequest:
    return InternalRequest(
        messages=[Message(role="user", content=text)],
        model="daari",
    )


def test_extract_location():
    assert "Paris" in extract_location("weather in Paris?")
    assert extract_location("@weather Tokyo")


def test_load_sources_config_defaults(tmp_path):
    cfg = load_sources_config(tmp_path / "missing.yaml")
    assert "open-meteo" in cfg.priority
    assert "@weather" in (cfg.providers["open-meteo"]["triggers"])


def test_load_sources_config_file(tmp_path):
    path = tmp_path / "sources.yaml"
    path.write_text(
        yaml.dump(
            {
                "priority": ["wttr", "open-meteo"],
                "providers": {
                    "wttr": {"type": "wttr", "triggers": ["@wttr"]},
                    "open-meteo": {"type": "open-meteo", "triggers": ["@weather"]},
                    "generic": {
                        "type": "generic-rest",
                        "triggers": ["@source"],
                        "endpoints": [{"id": "ping", "url": "http://example/ping"}],
                    },
                },
            }
        )
    )
    cfg = load_sources_config(path)
    assert cfg.priority[0] == "wttr"
    triggers = live_triggers(cfg)
    # Highest-priority weather provider also gets the bare @weather trigger.
    assert triggers["live:wttr"][0] == "@weather"
    assert "@wttr" in triggers["live:wttr"]
    assert "@weather" in triggers["live:open-meteo"]


@pytest.mark.asyncio
async def test_open_meteo_formats_forecast(monkeypatch):
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        if "geocoding" in str(request.url):
            return httpx.Response(
                200,
                json={"results": [{"name": "Paris", "latitude": 48.8, "longitude": 2.3}]},
            )
        return httpx.Response(
            200,
            json={"current": {"temperature_2m": 18.5, "relative_humidity_2m": 60, "weather_code": 1}},
        )

    transport = httpx.MockTransport(handler)
    provider = OpenMeteoProvider()

    async def execute_with_transport(request):
        # Patch AsyncClient used inside execute by temporarily monkeypatching httpx.
        real_client = httpx.AsyncClient

        class Patched(real_client):
            def __init__(self, *args, **kwargs):
                kwargs["transport"] = transport
                super().__init__(*args, **kwargs)

        monkeypatch.setattr(httpx, "AsyncClient", Patched)
        return await OpenMeteoProvider.execute(provider, request)

    result = await execute_with_transport(_req("@weather Paris"))
    assert "Paris" in result.content and "18.5" in result.content
    assert result.daari_meta.provider_id == "live:open-meteo"


@pytest.mark.asyncio
async def test_wttr_provider(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="Paris: ⛅️ +18°C")

    class Patched(httpx.AsyncClient):
        def __init__(self, *args, **kwargs):
            kwargs["transport"] = httpx.MockTransport(handler)
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", Patched)
    result = await WttrProvider().execute(_req("@wttr Paris"))
    assert "Paris" in result.content
    assert result.daari_meta.provider_id == "live:wttr"


@pytest.mark.asyncio
async def test_generic_rest(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text='{"ok":true}')

    class Patched(httpx.AsyncClient):
        def __init__(self, *args, **kwargs):
            kwargs["transport"] = httpx.MockTransport(handler)
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", Patched)
    provider = GenericRestProvider(endpoints=[{"id": "ping", "url": "http://example/ping"}])
    result = await provider.execute(_req("@source ping"))
    assert "ok" in result.content


@pytest.mark.asyncio
async def test_router_routes_weather_trigger(tmp_path, monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        if "geocoding" in str(request.url):
            return httpx.Response(
                200, json={"results": [{"name": "Berlin", "latitude": 52.5, "longitude": 13.4}]}
            )
        return httpx.Response(
            200,
            json={"current": {"temperature_2m": 10, "relative_humidity_2m": 80, "weather_code": 3}},
        )

    class Patched(httpx.AsyncClient):
        def __init__(self, *args, **kwargs):
            kwargs["transport"] = httpx.MockTransport(handler)
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", Patched)
    registry = ProviderRegistry()
    registry.register(OpenMeteoProvider())
    router = Router(
        cache=ExactCache(str(tmp_path / "l0"), enabled=False),
        semantic_cache=SemanticCache(str(tmp_path / "l1"), NoopEmbedder(), enabled=False),
        ollama=OllamaExecutor(base_url="http://t", default_model="llama3.2:3b"),
        metrics=Metrics(),
        frontier_enabled=False,
        provider_registry=registry,
        integration_triggers={"live:open-meteo": ["@weather"]},
    )
    result = await router.route(_req("@weather Berlin"))
    assert result.daari_meta.provider_id == "live:open-meteo"
    assert "Berlin" in result.content
