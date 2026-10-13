"""Hermetic scrape exposes per-scope in-flight gauges (#1612)."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from daari.auth.rate_limit import MemoryCounterBackend, RateLimiter
from daari.auth.virtual_keys import VirtualKeyStore
from daari.config.settings import ModelRateLimitSettings
from daari.observability.metrics_listen import prometheus_text_for_app
from daari.router.router import AppContext
from daari.server.app import create_app


def _app_with_caps(settings, tmp_path):
    settings.server.api_key = ""
    settings.observability.prometheus = True
    settings.server.virtual_keys.path = str(tmp_path / "vk.sqlite3")
    settings.rate_limit.models = {
        "llama3-70b": ModelRateLimitSettings(max_in_flight=2),
    }
    store = VirtualKeyStore(settings.virtual_keys_path)
    team = store.create_team("fleet", max_in_flight=3)
    created = store.create("agent", max_in_flight=1, team=team.name)
    limiter = RateLimiter(MemoryCounterBackend(), max_in_flight=0)
    # Seed used counts without going through admission.
    limiter._adjust_gauge(f"inflight:key:{created.key.key_id}", 1)
    limiter._adjust_gauge(f"inflight:team:{team.team_id}", 2)
    limiter._adjust_gauge("inflight:model:llama3-70b", 1)
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    app.state.virtual_key_store = store
    app.state.ctx.virtual_key_store = store
    app.state.rate_limiter = limiter
    return app, store, created, team


def test_prometheus_text_exposes_scoped_in_flight_gauges(settings, tmp_path):
    app, _store, created, team = _app_with_caps(settings, tmp_path)
    text = prometheus_text_for_app(app)
    assert text is not None
    assert "# TYPE daari_in_flight gauge" in text
    assert "# TYPE daari_in_flight_max gauge" in text
    assert 'daari_in_flight{scope="key",id="agent"} 1' in text
    assert 'daari_in_flight_max{scope="key",id="agent"} 1' in text
    assert 'daari_in_flight{scope="team",id="fleet"} 2' in text
    assert 'daari_in_flight_max{scope="team",id="fleet"} 3' in text
    assert 'daari_in_flight{scope="model",id="llama3-70b"} 1' in text
    assert 'daari_in_flight_max{scope="model",id="llama3-70b"} 2' in text
    # Never label with secrets / key ids when a name exists.
    assert created.key.key_id not in text or "agent" in text
    assert team.team_id not in text or "fleet" in text


@pytest.mark.asyncio
async def test_metrics_endpoint_exposes_scoped_in_flight(settings, tmp_path):
    app, _store, _created, _team = _app_with_caps(settings, tmp_path)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/metrics")
    assert response.status_code == 200
    assert 'daari_in_flight{scope="key",id="agent"} 1' in response.text
    assert 'daari_in_flight_max{scope="team",id="fleet"} 3' in response.text
