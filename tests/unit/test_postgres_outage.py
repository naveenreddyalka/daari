"""Postgres outage: VK fail-closed, budget degrade signal, /ready probe (#1652)."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from daari.auth.postgres_virtual_keys import (
    PostgresBackendUnavailable,
    PostgresVirtualKeyStore,
)
from daari.config.settings import Settings
from daari.observability.postgres_usage import PostgresUsageLedger
from daari.observability.prometheus import render_prometheus
from daari.router.router import AppContext
from daari.server.app import create_app
from daari.server.auth import resolve_auth, store_enforces_auth
from daari.setup.doctor import _check_postgres_stores


def test_vk_boot_failure_keeps_auth_enforced():
    store = PostgresVirtualKeyStore("postgresql://127.0.0.1:1/nope", enabled=True)
    assert store.enabled is True
    assert store.unreachable is True
    assert store_enforces_auth(store) is True


def test_vk_resolve_raises_unavailable_not_500():
    store = PostgresVirtualKeyStore("postgresql://127.0.0.1:1/nope", enabled=True)
    with pytest.raises(PostgresBackendUnavailable):
        store.resolve("sk-test")


def test_resolve_auth_surfaces_backend_unavailable():
    store = PostgresVirtualKeyStore("postgresql://127.0.0.1:1/nope", enabled=True)
    with pytest.raises(PostgresBackendUnavailable):
        resolve_auth("sk-test", master_key=None, store=store)


@pytest.mark.asyncio
async def test_gateway_vk_postgres_down_fails_closed(settings: Settings, monkeypatch):
    settings.server.api_key = ""
    settings.server.dangerously_permit_weak_or_unset_api_key = True
    settings.server.virtual_keys.backend = "postgres"
    settings.observability.postgres_url = "postgresql://127.0.0.1:1/nope"

    async def backend_ok(probe_url: str, timeout: float = 2.0) -> str:
        return "ok"

    monkeypatch.setattr("daari.gateway.openai.check_model_backend", backend_ok)
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    store = getattr(app.state, "virtual_key_store", None)
    assert store is not None
    assert store_enforces_auth(store) is True

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        open_resp = await client.post(
            "/v1/chat/completions",
            json={"model": "daari", "messages": [{"role": "user", "content": "hi"}]},
        )
        assert open_resp.status_code in (401, 503)
        body = open_resp.json()
        assert body["error"]["code"] == "postgres_unavailable"

        keyed = await client.post(
            "/v1/chat/completions",
            headers={"Authorization": "Bearer sk-anything"},
            json={"model": "daari", "messages": [{"role": "user", "content": "hi"}]},
        )
        assert keyed.status_code in (401, 503)
        assert keyed.json()["error"]["code"] == "postgres_unavailable"


def test_budget_spend_marks_soft_allow_degraded():
    ledger = PostgresUsageLedger("postgresql://127.0.0.1:1/nope", enabled=True)
    # Boot may mark unreachable; force a spend path that catches query errors.
    ledger.enabled = True
    ledger.unreachable = False
    spend = ledger.frontier_spend_usd_for_client("c1", window="day")
    assert spend == 0.0
    snap = ledger.budget_degrade_snapshot()
    assert snap["degraded"] is True
    assert snap["degrade_mode"] == "soft_allow"


def test_budget_degraded_prometheus_gauge():
    from daari.observability.metrics import Metrics

    text = render_prometheus(
        Metrics(),
        budget_degrade={"degraded": True, "degrade_mode": "soft_allow"},
    )
    assert 'daari_budget_degraded{mode="soft_allow"} 1' in text


@pytest.mark.asyncio
async def test_ready_includes_postgres_when_vk_backend_postgres(
    settings: Settings, monkeypatch
):
    settings.server.virtual_keys.backend = "postgres"
    settings.observability.postgres_url = "postgresql://127.0.0.1:1/nope"
    settings.server.dangerously_permit_weak_or_unset_api_key = True

    async def backend_ok(probe_url: str, timeout: float = 2.0) -> str:
        return "ok"

    monkeypatch.setattr("daari.gateway.openai.check_model_backend", backend_ok)
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/ready")
    body = response.json()
    assert "postgres" in body["checks"]
    assert body["checks"]["postgres"] != "ok"
    assert body["status"] in ("degraded", "not_ready")


def test_doctor_reports_per_store_postgres(settings: Settings):
    settings.server.virtual_keys.backend = "postgres"
    settings.observability.backend = "postgres"
    settings.observability.postgres_url = "postgresql://127.0.0.1:1/nope"
    results = _check_postgres_stores(settings)
    by_name = {r.name: r for r in results}
    assert "postgres.virtual_keys" in by_name
    assert "postgres.usage" in by_name
    assert by_name["postgres.virtual_keys"].ok is False
    assert by_name["postgres.usage"].ok is False


def test_docs_matrix_mentions_fail_closed_and_soft_allow():
    from pathlib import Path

    doc = Path("docs/developer/guides/configuration/auth-and-keys.md").read_text()
    assert "Postgres outage semantics" in doc
    assert "fail-closed" in doc
    assert "soft_allow" in doc or "X-Daari-Budget-Degraded" in doc
    assert "fail-open" in doc
