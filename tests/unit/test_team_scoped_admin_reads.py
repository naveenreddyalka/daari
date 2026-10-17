"""Team-scoped reads on /v1/daari traces, stats, and report (#1677)."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from daari.auth.virtual_keys import VirtualKeyStore
from daari.enterprise.rbac import resolve_team_read_filter
from daari.observability.trace import RequestTrace, TraceStore
from daari.router.router import AppContext
from daari.server.app import create_app


def test_resolve_team_read_filter_admin_any():
    assert resolve_team_read_filter(role="admin", caller_team_id=None, requested="t-b") == "t-b"
    assert resolve_team_read_filter(role="admin", caller_team_id="t-a", requested=None) is None


def test_resolve_team_read_filter_vk_bound_forbidden():
    with pytest.raises(PermissionError):
        resolve_team_read_filter(role="analyst", caller_team_id="t-a", requested="t-b")


def test_resolve_team_read_filter_vk_bound_auto_scope():
    assert (
        resolve_team_read_filter(role="analyst", caller_team_id="t-a", requested=None) == "t-a"
    )
    assert (
        resolve_team_read_filter(role="analyst", caller_team_id="t-a", requested="t-a") == "t-a"
    )


def test_trace_store_filters_by_team(tmp_path):
    store = TraceStore(path=tmp_path / "traces.sqlite3")
    for team in ("team-a", "team-b", "team-a"):
        trace = RequestTrace()
        trace.add("served", tier="L3")
        store.save(trace, tier="L3", category="chat", team_id=team)

    only_a = store.list(limit=20, team_id="team-a")
    assert len(only_a) == 2
    assert all(row["team_id"] == "team-a" for row in only_a)
    assert len(store.list(limit=20, team_id="team-b")) == 1
    assert len(store.list(limit=20)) == 3


def _app_with_teams(settings, tmp_path):
    settings.server.api_key = "master-sekret"
    settings.server.virtual_keys.enabled = True
    settings.server.virtual_keys.path = str(tmp_path / "vk.sqlite3")
    settings.trace.enabled = True
    settings.trace.path = str(tmp_path / "traces.sqlite3")
    settings.usage.path = str(tmp_path / "usage.sqlite3")
    settings.enterprise.sso.enabled = False
    store = VirtualKeyStore(settings.virtual_keys_path)
    team_a = store.create_team("alpha")
    team_b = store.create_team("beta")
    key_a = store.create("alice", team=team_a.name, client_id="alice")
    key_b = store.create("bob", team=team_b.name, client_id="bob")
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    app.state.virtual_key_store = store
    app.state.ctx.virtual_key_store = store
    return app, store, key_a, key_b, team_a, team_b


@pytest.mark.asyncio
async def test_vk_team_a_cannot_read_team_b_traces(settings, tmp_path):
    app, _store, key_a, _key_b, team_a, team_b = _app_with_teams(settings, tmp_path)
    ctx = app.state.ctx
    for team_id in (team_a.team_id, team_b.team_id):
        trace = RequestTrace()
        trace.add("served", tier="L3")
        ctx.router.trace_store.save(trace, tier="L3", category="chat", team_id=team_id)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        forbidden = await client.get(
            f"/v1/daari/traces?team_id={team_b.team_id}",
            headers={"Authorization": f"Bearer {key_a.plaintext}"},
        )
        assert forbidden.status_code == 403

        forbidden_stats = await client.get(
            f"/v1/daari/stats?team_id={team_b.team_id}",
            headers={"Authorization": f"Bearer {key_a.plaintext}"},
        )
        assert forbidden_stats.status_code == 403

        forbidden_report = await client.get(
            f"/v1/daari/report?team_id={team_b.team_id}",
            headers={"Authorization": f"Bearer {key_a.plaintext}"},
        )
        assert forbidden_report.status_code == 403

        ok = await client.get(
            f"/v1/daari/traces?team_id={team_a.team_id}",
            headers={"Authorization": f"Bearer {key_a.plaintext}"},
        )
        assert ok.status_code == 200
        traces = ok.json()["traces"]
        assert len(traces) == 1
        assert traces[0]["team_id"] == team_a.team_id


@pytest.mark.asyncio
async def test_master_may_filter_any_team(settings, tmp_path):
    app, _store, _key_a, _key_b, team_a, team_b = _app_with_teams(settings, tmp_path)
    ctx = app.state.ctx
    for team_id in (team_a.team_id, team_b.team_id, team_a.team_id):
        trace = RequestTrace()
        trace.add("served", tier="L3")
        ctx.router.trace_store.save(trace, tier="L3", category="chat", team_id=team_id)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(
            f"/v1/daari/traces?team_id={team_b.team_id}",
            headers={"Authorization": "Bearer master-sekret"},
        )
        assert resp.status_code == 200
        assert len(resp.json()["traces"]) == 1
        assert resp.json()["traces"][0]["team_id"] == team_b.team_id


@pytest.mark.asyncio
async def test_scoped_trace_detail_hides_other_team(settings, tmp_path):
    app, _store, key_a, _key_b, team_a, team_b = _app_with_teams(settings, tmp_path)
    ctx = app.state.ctx
    trace_b = RequestTrace()
    trace_b.add("served", tier="L3")
    ctx.router.trace_store.save(trace_b, tier="L3", category="chat", team_id=team_b.team_id)
    trace_a = RequestTrace()
    trace_a.add("served", tier="L3")
    ctx.router.trace_store.save(trace_a, tier="L3", category="chat", team_id=team_a.team_id)
    alice = {"Authorization": f"Bearer {key_a.plaintext}"}
    master = {"Authorization": "Bearer master-sekret"}

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        denied = await client.get(f"/v1/daari/traces/{trace_b.trace_id}", headers=alice)
        assert denied.status_code in (403, 404)
        own = await client.get(f"/v1/daari/traces/{trace_a.trace_id}", headers=alice)
        assert own.status_code == 200
        assert own.json()["team_id"] == team_a.team_id
        admin = await client.get(f"/v1/daari/traces/{trace_b.trace_id}", headers=master)
        assert admin.status_code == 200
        assert admin.json()["trace_id"] == trace_b.trace_id


@pytest.mark.asyncio
async def test_scoped_report_hides_other_team_dollars(settings, tmp_path):
    app, _store, key_a, _key_b, team_a, _team_b = _app_with_teams(settings, tmp_path)
    ledger = app.state.ctx.router.usage_ledger
    ledger.record(
        tier="L6",
        client_id="alice",
        model="gpt-4o",
        input_tokens=1_000_000,
        output_tokens=0,
    )
    ledger.record(
        tier="L6",
        client_id="bob",
        model="gpt-4o",
        input_tokens=2_000_000,
        output_tokens=0,
    )
    alice = {"Authorization": f"Bearer {key_a.plaintext}"}
    master = {"Authorization": "Bearer master-sekret"}

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        scoped = await client.get(
            f"/v1/daari/report?team_id={team_a.team_id}&days=1",
            headers=alice,
        )
        assert scoped.status_code == 200
        body = scoped.json()
        assert body["frontier"]["today_spend_usd"] == pytest.approx(2.5, abs=0.02)
        assert body["frontier"]["month_spend_usd"] == pytest.approx(2.5, abs=0.02)
        assert body["totals"]["frontier_requests"] == 1
        for row in body.get("team_model_spend") or []:
            assert row.get("team_id") == team_a.team_id
        admin = await client.get("/v1/daari/report?days=1", headers=master)
        assert admin.status_code == 200
        fleet = admin.json()
        assert fleet["frontier"]["today_spend_usd"] == pytest.approx(7.5, abs=0.05)
        assert fleet["totals"]["frontier_requests"] == 2


@pytest.mark.asyncio
async def test_scoped_stats_zero_fleet_counters(settings, tmp_path):
    app, _store, key_a, _key_b, team_a, _team_b = _app_with_teams(settings, tmp_path)
    metrics = app.state.ctx.metrics
    metrics.record("L3", cache_hit=False, latency_ms=12)
    metrics.record_error(status=500)
    alice = {"Authorization": f"Bearer {key_a.plaintext}"}
    master = {"Authorization": "Bearer master-sekret"}

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        scoped = await client.get(
            f"/v1/daari/stats?team_id={team_a.team_id}",
            headers=alice,
        )
        assert scoped.status_code == 200
        data = scoped.json()
        assert data["total_requests"] == 0
        assert data["errors"] == 0
        assert data["tiers"] == {}
        admin = await client.get("/v1/daari/stats", headers=master)
        assert admin.status_code == 200
        fleet = admin.json()
        assert fleet["total_requests"] >= 1
        assert fleet["errors"] >= 1
        assert fleet["tiers"]


def test_auth_and_keys_docs_scoped_reads() -> None:
    from pathlib import Path

    text = Path("docs/developer/guides/configuration/auth-and-keys.md").read_text(
        encoding="utf-8"
    )
    assert "team_id" in text
    assert "scoped" in text.lower() or "?team_id=" in text
    assert "/v1/daari/traces" in text
    assert "/v1/daari/stats" in text
    assert "/v1/daari/report" in text
