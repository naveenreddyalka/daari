"""Hermetic scrape refreshes daari_virtual_keys gauge (#1566)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import httpx
import pytest
from httpx import ASGITransport, AsyncClient

from daari.auth.virtual_keys import VirtualKeyStore
from daari.observability.key_expiry_alerts import KeyExpiryAlerter
from daari.observability.metrics_listen import prometheus_text_for_app
from daari.router.router import AppContext
from daari.server.app import create_app


def _app_with_vk_store(settings, tmp_path):
    settings.server.api_key = ""
    settings.observability.prometheus = True
    settings.server.virtual_keys.path = str(tmp_path / "vk.sqlite3")
    settings.alerts.key_expiry_warn_days = 14
    store = VirtualKeyStore(settings.virtual_keys_path)
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    app.state.virtual_key_store = store
    app.state.ctx.virtual_key_store = store
    return app, store


def _seed_mixed_expiry(store: VirtualKeyStore, *, now: datetime) -> None:
    store.create("active", expires_at=(now + timedelta(days=90)).isoformat())
    store.create("soon", expires_at=(now + timedelta(days=3)).isoformat())
    store.create("dead", expires_at=(now - timedelta(days=1)).isoformat())
    revoked = store.create("rev", expires_at=(now + timedelta(days=30)).isoformat())
    store.revoke(revoked.key.key_id)


def test_prometheus_text_for_app_refreshes_virtual_keys_gauge(settings, tmp_path):
    app, store = _app_with_vk_store(settings, tmp_path)
    now = datetime.now(timezone.utc)
    _seed_mixed_expiry(store, now=now)

    text = prometheus_text_for_app(app)
    assert text is not None
    assert "# TYPE daari_virtual_keys gauge" in text
    assert 'daari_virtual_keys{status="active"} 1' in text
    assert 'daari_virtual_keys{status="expiring_soon"} 1' in text
    assert 'daari_virtual_keys{status="expired"} 1' in text
    assert 'daari_virtual_keys{status="revoked"} 1' in text


@pytest.mark.asyncio
async def test_metrics_endpoint_exposes_virtual_keys_gauge(settings, tmp_path):
    app, store = _app_with_vk_store(settings, tmp_path)
    now = datetime.now(timezone.utc)
    _seed_mixed_expiry(store, now=now)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/metrics")
    assert response.status_code == 200
    assert 'daari_virtual_keys{status="active"} 1' in response.text
    assert 'daari_virtual_keys{status="expiring_soon"} 1' in response.text
    assert 'daari_virtual_keys{status="expired"} 1' in response.text
    assert 'daari_virtual_keys{status="revoked"} 1' in response.text


def test_scrape_posts_key_expiry_webhook_once(settings, tmp_path):
    """Entering the warn window on scrape posts once via key_expiry_alerter."""
    app, store = _app_with_vk_store(settings, tmp_path)
    now = datetime.now(timezone.utc)
    store.create("soon", expires_at=(now + timedelta(days=5)).isoformat())
    store.create("far", expires_at=(now + timedelta(days=40)).isoformat())

    posted: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        posted.append(request)
        return httpx.Response(204)

    app.state.key_expiry_alerter = KeyExpiryAlerter(
        webhook_url="https://hooks.example/key-expiry",
        warn_days=14,
        transport=httpx.MockTransport(handler),
    )

    first = prometheus_text_for_app(app)
    assert first is not None
    assert 'daari_virtual_keys{status="expiring_soon"} 1' in first
    assert len(posted) == 1

    second = prometheus_text_for_app(app)
    assert second is not None
    assert len(posted) == 1
