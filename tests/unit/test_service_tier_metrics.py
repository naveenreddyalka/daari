"""Stats / Prometheus counters for service_tier_not_allowed (#2110)."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from daari.auth.virtual_keys import VirtualKeyStore
from daari.gateway.internal import DaariMeta, InternalRequest, InternalResponse
from daari.observability.metrics import Metrics
from daari.observability.prometheus import render_prometheus
from daari.router.router import AppContext
from daari.server.app import create_app

CHAT = {
    "model": "llama3.2:3b",
    "messages": [{"role": "user", "content": "hi"}],
    "service_tier": "priority",
}


def test_prometheus_renders_service_tier_kinds() -> None:
    metrics = Metrics()
    metrics.record_reject("service_tier_not_allowed")
    metrics.record_soft_warning("service_tier_not_allowed_degraded")
    text = render_prometheus(metrics)
    assert 'daari_rejects_total{kind="service_tier_not_allowed"} 1' in text
    assert 'daari_soft_warnings_total{kind="service_tier_not_allowed_degraded"} 1' in text


def _mock_execute(app) -> None:
    async def fake(request: InternalRequest) -> InternalResponse:
        warning = getattr(request.sampling, "gate_warning", None)
        return InternalResponse(
            content="ok",
            model=request.model or "llama3.2:3b",
            daari_meta=DaariMeta(
                tier="L3",
                executor="ollama",
                latency_ms=1,
                warning=warning,
            ),
        )

    app.state.ctx.router.route = fake
    app.state.ctx.router.ollama.execute = fake


def _app(settings, tmp_path):
    settings.server.api_key = "master"
    settings.server.virtual_keys.path = str(tmp_path / "vk.sqlite3")
    settings.cache.l0.enabled = False
    settings.cache.l1.enabled = False
    settings.observability.prometheus = True
    store = VirtualKeyStore(settings.virtual_keys_path)
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    app.state.virtual_key_store = store
    app.state.ctx.virtual_key_store = store
    _mock_execute(app)
    return app, store


@pytest.mark.asyncio
async def test_deny_bumps_reject_counter(settings, tmp_path) -> None:
    app, store = _app(settings, tmp_path)
    locked = store.create("locked", allowed_service_tiers=["default"])
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        denied = await client.post(
            "/v1/chat/completions",
            json=CHAT,
            headers={
                "Authorization": f"Bearer {locked.plaintext}",
                "X-Daari-No-Cache": "true",
            },
        )
        assert denied.status_code == 403
        metrics = await client.get("/metrics", headers={"Authorization": "Bearer master"})
    assert 'daari_rejects_total{kind="service_tier_not_allowed"} 1' in metrics.text
    assert "service_tier_not_allowed_degraded" not in metrics.text
    assert app.state.ctx.metrics.rejects.get("service_tier_not_allowed") == 1
    assert app.state.ctx.metrics.soft_warnings.get("service_tier_not_allowed_degraded") is None


@pytest.mark.asyncio
async def test_degrade_bumps_soft_warning_counter(settings, tmp_path) -> None:
    app, store = _app(settings, tmp_path)
    degrade = store.create(
        "degrade",
        allowed_service_tiers=["default"],
        degrade_disallowed_service_tier=True,
    )
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        ok = await client.post(
            "/v1/chat/completions",
            json=CHAT,
            headers={
                "Authorization": f"Bearer {degrade.plaintext}",
                "X-Daari-No-Cache": "true",
                "X-Daari-Meta": "true",
            },
        )
        assert ok.status_code == 200
        assert "service_tier_not_allowed_degraded" in (
            (ok.json().get("daari_meta") or {}).get("warning") or ""
        )
        metrics = await client.get("/metrics", headers={"Authorization": "Bearer master"})
    assert 'daari_soft_warnings_total{kind="service_tier_not_allowed_degraded"} 1' in metrics.text
    assert 'daari_rejects_total{kind="service_tier_not_allowed"}' not in metrics.text
    assert app.state.ctx.metrics.soft_warnings.get("service_tier_not_allowed_degraded") == 1
    assert app.state.ctx.metrics.rejects.get("service_tier_not_allowed") is None


@pytest.mark.asyncio
async def test_absent_allowlist_leaves_counters_unchanged(settings, tmp_path) -> None:
    app, store = _app(settings, tmp_path)
    open_key = store.create("open")
    before_rejects = dict(app.state.ctx.metrics.rejects)
    before_soft = dict(app.state.ctx.metrics.soft_warnings)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        ok = await client.post(
            "/v1/chat/completions",
            json=CHAT,
            headers={
                "Authorization": f"Bearer {open_key.plaintext}",
                "X-Daari-No-Cache": "true",
            },
        )
        assert ok.status_code == 200
    assert app.state.ctx.metrics.rejects.get("service_tier_not_allowed") == before_rejects.get(
        "service_tier_not_allowed"
    )
    assert app.state.ctx.metrics.soft_warnings.get(
        "service_tier_not_allowed_degraded"
    ) == before_soft.get("service_tier_not_allowed_degraded")
