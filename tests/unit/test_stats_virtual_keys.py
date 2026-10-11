"""GET /v1/daari/stats exposes virtual_keys lifecycle counts (#1573)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from daari.auth.virtual_keys import VirtualKeyStore
from daari.router.router import AppContext
from daari.server.app import create_app

DOC_METRICS = (
    Path(__file__).resolve().parents[2]
    / "docs/developer/guides/observability/metrics-prometheus.md"
)
DOC_TRACES = (
    Path(__file__).resolve().parents[2] / "docs/developer/guides/observability/traces-stats.md"
)


def _app_with_vk_store(settings, tmp_path):
    settings.server.api_key = "master"
    settings.server.virtual_keys.path = str(tmp_path / "vk.sqlite3")
    settings.alerts.key_expiry_warn_days = 14
    store = VirtualKeyStore(settings.virtual_keys_path)
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    app.state.virtual_key_store = store
    app.state.ctx.virtual_key_store = store
    return app, store


_AUTH = {"Authorization": "Bearer master"}


def _seed_mixed_expiry(store: VirtualKeyStore, *, now: datetime) -> None:
    store.create("active", expires_at=(now + timedelta(days=90)).isoformat())
    store.create("soon", expires_at=(now + timedelta(days=3)).isoformat())
    store.create("dead", expires_at=(now - timedelta(days=1)).isoformat())
    revoked = store.create("rev", expires_at=(now + timedelta(days=30)).isoformat())
    store.revoke(revoked.key.key_id)


@pytest.mark.asyncio
async def test_stats_virtual_keys_zeros_when_empty(settings, tmp_path):
    app, _store = _app_with_vk_store(settings, tmp_path)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/v1/daari/stats", headers=_AUTH)
    assert response.status_code == 200
    assert response.json()["virtual_keys"] == {
        "active": 0,
        "expired": 0,
        "expiring_soon": 0,
        "revoked": 0,
    }


@pytest.mark.asyncio
async def test_stats_virtual_keys_mixed_lifecycle(settings, tmp_path):
    app, store = _app_with_vk_store(settings, tmp_path)
    now = datetime.now(timezone.utc)
    _seed_mixed_expiry(store, now=now)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/v1/daari/stats", headers=_AUTH)
    assert response.status_code == 200
    assert response.json()["virtual_keys"] == {
        "active": 1,
        "expired": 1,
        "expiring_soon": 1,
        "revoked": 1,
    }


def test_docs_note_stats_virtual_keys_counterpart() -> None:
    metrics = DOC_METRICS.read_text(encoding="utf-8")
    traces = DOC_TRACES.read_text(encoding="utf-8")
    assert "virtual_keys" in metrics
    assert "/v1/daari/stats" in metrics
    assert "virtual_keys" in traces
    assert "daari_virtual_keys" in traces or "metrics-prometheus" in traces
