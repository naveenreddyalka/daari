"""Per-family breaker state, stats inventory, reset, and doctor (#1932)."""

from __future__ import annotations

import re

import httpx
import pytest
from httpx import ASGITransport, AsyncClient

from daari.router.circuit_breaker import CircuitBreaker
from daari.router.router import AppContext
from daari.server.app import create_app


def test_prometheus_exports_breaker_state_per_family(settings, monkeypatch):
    from daari.gateway.systemone import (
        _note_failure,
        breaker_for,
        reset_systemone_breakers,
    )
    from daari.observability.metrics import Metrics
    from daari.observability.prometheus import render_prometheus
    from daari.router import breaker_inventory

    reset_systemone_breakers()
    metrics = Metrics()
    breaker = breaker_for("http://vllm.local:8000")
    breaker.failure_threshold = 1
    breaker.cooldown_seconds = 60.0
    _note_failure("http://vllm.local:8000", metrics=metrics)

    frontier = CircuitBreaker(failure_threshold=1, cooldown_seconds=60.0, share_key="frontier:openai")
    frontier.record_failure()
    metrics.record_breaker(family="frontier", event="open")
    metrics.record_breaker(family="frontier", event="trip")

    local = CircuitBreaker(failure_threshold=1, cooldown_seconds=60.0, share_key="local:gpu-a")
    local.record_failure()
    metrics.record_breaker(family="local_pool", event="open")

    mcp = CircuitBreaker(failure_threshold=1, cooldown_seconds=60.0, share_key="mcp:weather")
    mcp.record_failure()
    metrics.record_breaker(family="mcp_egress", event="open")

    inventory = breaker_inventory.collect_breaker_inventory(
        frontier_slots=[("openai", frontier)],
        local_slots=[("gpu-a", local)],
        mcp_slots=[("weather", mcp)],
    )
    monkeypatch.setattr(
        Metrics,
        "_breaker_state",
        lambda self: inventory,
    )
    text = render_prometheus(metrics)

    assert "daari_breaker_state" in text
    assert 'family="systemone"' in text or any(
        r.get("family") == "systemone" for r in inventory
    )
    assert 'family="frontier"' in text
    assert 'family="local_pool"' in text
    assert 'family="mcp_egress"' in text
    assert re.search(r'daari_breaker_state\{[^}]*family="frontier"[^}]*\} 1', text)
    assert "daari_breaker_total" in text
    assert 'event="open"' in text
    assert "daari_systemone_breaker_state" in text


def test_stats_includes_breaker_inventory(settings):
    from daari.gateway.systemone import _note_failure, breaker_for, reset_systemone_breakers
    from daari.router.breaker_inventory import collect_breaker_inventory

    reset_systemone_breakers()
    breaker = breaker_for("http://vllm.local:8000")
    breaker.failure_threshold = 1
    breaker.cooldown_seconds = 60.0
    _note_failure("http://vllm.local:8000")

    frontier = CircuitBreaker(failure_threshold=1, cooldown_seconds=60.0)
    frontier.record_failure()
    rows = collect_breaker_inventory(
        frontier_slots=[("openai", frontier)],
        local_slots=[],
        mcp_slots=[],
    )
    assert any(r["family"] == "systemone" and r["state"] == "open" for r in rows)
    assert any(
        r["family"] == "frontier" and r["target"] == "openai" and r["state"] == "open"
        for r in rows
    )
    assert all("opened_at" in r for r in rows)
    assert all("family" in r and "target" in r and "state" in r for r in rows)


@pytest.mark.asyncio
async def test_stats_endpoint_breaker_inventory(settings):
    from daari.gateway.systemone import _note_failure, breaker_for, reset_systemone_breakers

    reset_systemone_breakers()
    settings.server.api_key = "master-sekret"
    settings.enterprise.sso.enabled = False
    breaker = breaker_for("http://vllm.local:8000")
    breaker.failure_threshold = 1
    breaker.cooldown_seconds = 60.0
    _note_failure("http://vllm.local:8000")
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(
            "/v1/daari/stats",
            headers={"Authorization": "Bearer master-sekret"},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert "breakers" in body
    assert isinstance(body["breakers"], list)
    assert any(
        row.get("family") == "systemone" and row.get("state") == "open"
        for row in body["breakers"]
    )


@pytest.mark.asyncio
async def test_breakers_reset_route_requires_admin(settings, tmp_path):
    from daari.auth.virtual_keys import VirtualKeyStore
    from daari.gateway.systemone import reset_systemone_breakers

    reset_systemone_breakers()
    settings.server.api_key = "master-sekret"
    settings.server.virtual_keys.enabled = True
    settings.server.virtual_keys.path = str(tmp_path / "vk.sqlite3")
    settings.enterprise.sso.enabled = False
    store = VirtualKeyStore(settings.virtual_keys_path)
    key = store.create("viewer", client_id="viewer")
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    app.state.virtual_key_store = store
    app.state.ctx.virtual_key_store = store
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/v1/daari/breakers/reset",
            headers={"Authorization": f"Bearer {key.plaintext}"},
        )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_breakers_reset_closes_open_circuits(settings, tmp_path):
    from daari.gateway.systemone import (
        _note_failure,
        breaker_for,
        breaker_snapshot,
        reset_systemone_breakers,
    )

    reset_systemone_breakers()
    settings.server.api_key = "master-sekret"
    settings.enterprise.sso.enabled = False
    settings.enterprise.audit_path = str(tmp_path / "audit.sqlite3")
    breaker = breaker_for("http://vllm.local:8000")
    breaker.failure_threshold = 1
    breaker.cooldown_seconds = 60.0
    _note_failure("http://vllm.local:8000")
    assert breaker_snapshot()[0]["state"] == "open"

    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/v1/daari/breakers/reset",
            headers={"Authorization": "Bearer master-sekret"},
            json={"family": "systemone"},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert "breakers" in body
    assert all(
        row["state"] == "closed"
        for row in body["breakers"]
        if row.get("family") == "systemone"
    )
    assert breaker_snapshot()[0]["state"] == "closed"


def test_doctor_fleet_breaker_warns_when_open(settings):
    from unittest.mock import MagicMock

    from daari.gateway.systemone import _note_failure, breaker_for, reset_systemone_breakers
    from daari.setup.doctor import _check_fleet_breakers

    reset_systemone_breakers()
    breaker = breaker_for("http://vllm.local:8000")
    breaker.failure_threshold = 1
    _note_failure("http://vllm.local:8000")

    mock = MagicMock(spec=httpx.Client)
    mock.get.side_effect = httpx.ConnectError("refused")
    tip = _check_fleet_breakers(settings, httpx_client=mock)
    assert tip is not None
    assert tip.ok is False
    assert tip.name == "fleet_breakers"
    assert "systemone" in tip.detail
    assert "reset" in tip.detail.lower() or "cooldown" in tip.detail.lower()


def test_doctor_fleet_breaker_uses_daemon_stats(settings):
    from unittest.mock import MagicMock

    from daari.setup.doctor import _check_fleet_breakers

    mock = MagicMock(spec=httpx.Client)
    response = MagicMock()
    response.status_code = 200
    response.json.return_value = {
        "breakers": [
            {
                "family": "frontier",
                "target": "openai",
                "state": "open",
                "opened_at": 1.0,
            }
        ]
    }
    mock.get.return_value = response
    tip = _check_fleet_breakers(settings, httpx_client=mock)
    assert tip is not None
    assert tip.ok is False
    assert "frontier" in tip.detail
    assert "openai" in tip.detail
