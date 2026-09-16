"""Prometheus counters for hard 402/429 rejects (#551)."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from daari.auth.rate_limit import MemoryCounterBackend, RateLimiter
from daari.auth.virtual_keys import BudgetWindow, VirtualKeyStore
from daari.gateway.budget_headers import QUOTA_REQUESTS_WARNING_HEADER
from daari.gateway.internal import DaariMeta, InternalRequest, InternalResponse
from daari.observability.metrics import Metrics
from daari.observability.prometheus import render_prometheus
from daari.observability.usage import UsageLedger
from daari.router.router import AppContext
from daari.server.app import create_app

CHAT = {"model": "daari", "messages": [{"role": "user", "content": "hi"}]}


def test_rejects_prometheus_kinds():
    metrics = Metrics()
    metrics.record_reject("budget")
    metrics.record_reject("request_quota")
    metrics.record_reject("rate_limit")
    metrics.record_reject("rate_limit")
    text = render_prometheus(metrics)
    assert "# TYPE daari_rejects_total counter" in text
    assert 'daari_rejects_total{kind="budget"} 1' in text
    assert 'daari_rejects_total{kind="request_quota"} 1' in text
    assert 'daari_rejects_total{kind="rate_limit"} 2' in text


def _mock_execute(app):
    async def fake(request: InternalRequest) -> InternalResponse:
        return InternalResponse(
            content="ok",
            model="llama3.2:3b",
            daari_meta=DaariMeta(tier="L3", executor="ollama", latency_ms=1),
        )

    app.state.ctx.router.ollama.execute = fake


def _app_with_keys(settings, tmp_path):
    settings.server.api_key = "master"
    settings.server.virtual_keys.path = str(tmp_path / "vk.sqlite3")
    settings.usage.path = str(tmp_path / "usage.sqlite3")
    settings.observability.prometheus = True
    store = VirtualKeyStore(settings.virtual_keys_path)
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    app.state.virtual_key_store = store
    app.state.ctx.virtual_key_store = store
    _mock_execute(app)
    ledger = UsageLedger(tmp_path / "usage.sqlite3")
    app.state.ctx.router.usage_ledger = ledger
    return app, store, ledger


def _record_frontier_spend(ledger: UsageLedger, client_id: str, *, usd: float) -> None:
    """Record frontier usage at the flat fallback rate ($0.002 / 1k tokens)."""
    ledger.record(
        tier="L6",
        client_id=client_id,
        model="",
        input_tokens=int(usd / 0.002 * 1000),
        output_tokens=0,
    )


def _record_requests(ledger: UsageLedger, client_id: str, n: int) -> None:
    for _ in range(n):
        ledger.record(tier="L3", client_id=client_id, cache_hit=False)


@pytest.mark.asyncio
async def test_hard_budget_402_bumps_budget_reject(settings, tmp_path):
    app, store, ledger = _app_with_keys(settings, tmp_path)
    key = store.create("a", client_id="key-a", daily_budget_usd=1.0)
    _record_frontier_spend(ledger, "key-a", usd=1.0)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        hard = await client.post(
            "/v1/chat/completions",
            json=CHAT,
            headers={"Authorization": f"Bearer {key.plaintext}"},
        )
        assert hard.status_code == 402

        metrics = await client.get("/metrics", headers={"Authorization": "Bearer master"})
    assert metrics.status_code == 200
    assert 'daari_rejects_total{kind="budget"} 1' in metrics.text
    assert 'daari_rejects_total{kind="request_quota"}' not in metrics.text
    assert 'daari_soft_warnings_total' not in metrics.text or (
        'daari_soft_warnings_total{kind="request_quota"}' not in metrics.text
    )


@pytest.mark.asyncio
async def test_soft_request_quota_does_not_bump_rejects(settings, tmp_path):
    settings.frontier.soft_budget_ratio = 0.8
    app, store, ledger = _app_with_keys(settings, tmp_path)
    key = store.create(
        "a",
        client_id="key-a",
        budget_windows=[BudgetWindow("day", 0.0, max_requests=10)],
    )
    _record_requests(ledger, "key-a", 8)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        soft = await client.post(
            "/v1/chat/completions",
            json=CHAT,
            headers={
                "Authorization": f"Bearer {key.plaintext}",
                "X-Daari-No-Cache": "true",
            },
        )
        assert soft.status_code == 200
        assert soft.headers[QUOTA_REQUESTS_WARNING_HEADER] == "soft"

        metrics = await client.get("/metrics", headers={"Authorization": "Bearer master"})
    assert 'daari_soft_warnings_total{kind="request_quota"} 1' in metrics.text
    assert "daari_rejects_total" not in metrics.text


@pytest.mark.asyncio
async def test_hard_request_quota_402_bumps_request_quota_reject(settings, tmp_path):
    app, store, ledger = _app_with_keys(settings, tmp_path)
    key = store.create(
        "a",
        client_id="key-a",
        budget_windows=[BudgetWindow("day", 0.0, max_requests=1)],
    )
    _record_requests(ledger, "key-a", 1)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        hard = await client.post(
            "/v1/chat/completions",
            json=CHAT,
            headers={"Authorization": f"Bearer {key.plaintext}"},
        )
        assert hard.status_code == 402

        metrics = await client.get("/metrics", headers={"Authorization": "Bearer master"})
    assert 'daari_rejects_total{kind="request_quota"} 1' in metrics.text
    assert 'daari_rejects_total{kind="budget"}' not in metrics.text


@pytest.mark.asyncio
async def test_hard_429_bumps_rate_limit_reject(settings, monkeypatch):
    import time

    monkeypatch.setattr(time, "time", lambda: 1_700_000_030.0)
    settings.frontier.soft_budget_ratio = 0.0
    settings.observability.prometheus = True
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    app.state.rate_limiter = RateLimiter(MemoryCounterBackend(), default_rpm=1)
    _mock_execute(app)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        ok = await client.post(
            "/v1/chat/completions",
            json=CHAT,
            headers={"X-Daari-No-Cache": "true"},
        )
        assert ok.status_code == 200

        hard = await client.post("/v1/chat/completions", json=CHAT)
        assert hard.status_code == 429

        metrics = await client.get("/metrics")
    assert 'daari_rejects_total{kind="rate_limit"} 1' in metrics.text
    assert 'daari_soft_warnings_total{kind="rate_limit"}' not in metrics.text
