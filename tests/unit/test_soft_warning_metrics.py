"""Prometheus counters for soft rate-limit / request-quota warnings (#526)."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from daari.auth.rate_limit import RATELIMIT_WARNING_HEADER
from daari.auth.virtual_keys import BudgetWindow, VirtualKeyStore
from daari.gateway.budget_headers import QUOTA_REQUESTS_WARNING_HEADER
from daari.gateway.internal import DaariMeta, InternalRequest, InternalResponse
from daari.observability.metrics import Metrics
from daari.observability.prometheus import render_prometheus
from daari.observability.usage import UsageLedger
from daari.router.router import AppContext
from daari.server.app import create_app

CHAT = {"model": "daari", "messages": [{"role": "user", "content": "hi"}]}


def test_soft_warnings_prometheus_kinds():
    metrics = Metrics()
    metrics.record_soft_warning("request_quota")
    metrics.record_soft_warning("rate_limit")
    metrics.record_soft_warning("rate_limit")
    text = render_prometheus(metrics)
    assert "# TYPE daari_soft_warnings_total counter" in text
    assert 'daari_soft_warnings_total{kind="request_quota"} 1' in text
    assert 'daari_soft_warnings_total{kind="rate_limit"} 2' in text


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


def _record_requests(ledger: UsageLedger, client_id: str, n: int) -> None:
    for _ in range(n):
        ledger.record(tier="L3", client_id=client_id, cache_hit=False)


@pytest.mark.asyncio
async def test_request_quota_soft_increments_counter_hard_402_does_not(settings, tmp_path):
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
        assert metrics.status_code == 200
        assert 'daari_soft_warnings_total{kind="request_quota"} 1' in metrics.text

        _record_requests(ledger, "key-a", 2)
        hard = await client.post(
            "/v1/chat/completions",
            json=CHAT,
            headers={"Authorization": f"Bearer {key.plaintext}"},
        )
        assert hard.status_code == 402
        assert QUOTA_REQUESTS_WARNING_HEADER not in hard.headers

        after = await client.get("/metrics", headers={"Authorization": "Bearer master"})
    assert 'daari_soft_warnings_total{kind="request_quota"} 1' in after.text
    assert 'daari_soft_warnings_total{kind="rate_limit"}' not in after.text


@pytest.mark.asyncio
async def test_rate_limit_soft_increments_counter_hard_429_does_not(settings):
    settings.rate_limit.rpm = 5
    settings.frontier.soft_budget_ratio = 0.8
    settings.observability.prometheus = True
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    _mock_execute(app)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        for i in range(5):
            response = await client.post(
                "/v1/chat/completions",
                json=CHAT,
                headers={"X-Daari-No-Cache": "true"},
            )
            assert response.status_code == 200
            if i >= 3:
                assert response.headers[RATELIMIT_WARNING_HEADER] == "soft"

        metrics = await client.get("/metrics")
        assert 'daari_soft_warnings_total{kind="rate_limit"} 2' in metrics.text

        hard = await client.post("/v1/chat/completions", json=CHAT)
        assert hard.status_code == 429
        assert RATELIMIT_WARNING_HEADER not in hard.headers

        after = await client.get("/metrics")
    assert 'daari_soft_warnings_total{kind="rate_limit"} 2' in after.text
    assert 'daari_soft_warnings_total{kind="request_quota"}' not in after.text
