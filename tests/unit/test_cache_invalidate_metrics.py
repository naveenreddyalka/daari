"""Prometheus counters for admin cache invalidate (#1639)."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from daari.observability.metrics import Metrics
from daari.observability.prometheus import render_prometheus
from daari.router.router import AppContext
from daari.server.app import create_app
from tests.unit.test_cache_invalidate import _req, _resp


def test_cache_invalidate_prometheus_labels() -> None:
    metrics = Metrics()
    metrics.record_cache_invalidate(scope="model", result="ok", l0_removed=2, l1_removed=1)
    metrics.record_cache_invalidate(scope="all", result="ok")
    metrics.record_cache_invalidate(scope="hash", result="error")
    text = render_prometheus(metrics)
    assert "# TYPE daari_cache_invalidate_total counter" in text
    assert 'daari_cache_invalidate_total{scope="model",result="ok"} 1' in text
    assert 'daari_cache_invalidate_total{scope="all",result="ok"} 1' in text
    assert 'daari_cache_invalidate_total{scope="hash",result="error"} 1' in text
    assert "# TYPE daari_cache_invalidate_entries_removed_total counter" in text
    assert 'daari_cache_invalidate_entries_removed_total{layer="l0"} 2' in text
    assert 'daari_cache_invalidate_entries_removed_total{layer="l1"} 1' in text


def test_cache_invalidate_scope_helper() -> None:
    from daari.observability.metrics import cache_invalidate_scope

    assert cache_invalidate_scope(model="m") == "model"
    assert cache_invalidate_scope(entry_hash="abc") == "hash"
    assert cache_invalidate_scope(team_id="t") == "team"
    assert cache_invalidate_scope(key_id="k") == "key"
    assert cache_invalidate_scope(speed="fast") == "speed"
    assert cache_invalidate_scope() == "all"
    # hash wins over model when both set (most specific filter)
    assert cache_invalidate_scope(model="m", entry_hash="h") == "hash"
    # model wins over speed when both set
    assert cache_invalidate_scope(model="m", speed="fast") == "model"


@pytest.mark.asyncio
async def test_admin_invalidate_bumps_prometheus(settings) -> None:
    settings.observability.prometheus = True
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    app.state.ctx.router.cache.put(_req("cached"), _resp("answer", "llama"))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/daari/cache/invalidate",
            json={"model": "llama"},
        )
        assert response.status_code == 200
        assert response.json()["l0_removed"] == 1
        metrics = await client.get("/metrics")
    assert metrics.status_code == 200
    assert 'daari_cache_invalidate_total{scope="model",result="ok"} 1' in metrics.text
    assert 'daari_cache_invalidate_entries_removed_total{layer="l0"} 1' in metrics.text
