"""Frontier binding outcome counters on Prometheus and /v1/daari/stats (#2316)."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from daari.auth.frontier_binding import FrontierBindingError, record_frontier_binding
from daari.auth.virtual_keys import VirtualKeyStore
from daari.gateway.internal import (
    DaariMeta,
    InternalRequest,
    InternalResponse,
    Message,
    RequestMeta,
)
from daari.observability.metrics import Metrics
from daari.observability.prometheus import render_prometheus
from daari.router.frontier import FrontierExecutor
from daari.router.frontier_pool import FrontierPool, ProviderSlot
from daari.router.router import AppContext
from daari.security.secret_refs import SecretRefError
from daari.server.app import create_app
from daari.server.auth import AuthClaims, apply_auth_claims_to_meta


def _request(**meta_kwargs) -> InternalRequest:
    return InternalRequest(
        messages=[Message(role="user", content="escalate me")],
        model="daari",
        meta=RequestMeta(**meta_kwargs),
    )


def _ok(provider: str = "primary") -> InternalResponse:
    return InternalResponse(
        content=f"answer from {provider}",
        model="gpt-4o-mini",
        daari_meta=DaariMeta(
            tier="L6",
            executor="frontier",
            provider_id=provider,
            latency_ms=10,
            model="gpt-4o-mini",
        ),
    )


def _pool(metrics: Metrics | None) -> tuple[FrontierPool, list[str | None]]:
    captured: list[str | None] = []
    executor = FrontierExecutor(
        base_url="http://primary", default_model="a", api_key="sk-global", provider="primary"
    )

    async def ok(request, *, escalated_from, local_confidence):
        captured.append(executor.api_key)
        return _ok()

    executor.execute = ok  # type: ignore[method-assign]
    executor.metrics = metrics
    pool = FrontierPool(
        slots=[ProviderSlot(id="primary", executor=executor, keys=["sk-global"])]
    )
    return pool, captured


def test_metrics_record_frontier_binding_bounded_labels():
    metrics = Metrics()
    metrics.record_frontier_binding(outcome="signed", source="key")
    metrics.record_frontier_binding(outcome="signed", source="team")
    metrics.record_frontier_binding(outcome="pin_unmatched", source="team")
    metrics.record_frontier_binding(outcome="unresolvable", source="key")
    metrics.record_frontier_binding(outcome="unresolvable", source="key")
    # Unknown values collapse into fixed buckets — no per-tenant cardinality.
    metrics.record_frontier_binding(outcome="bogus", source="team-eng")
    snap = metrics.snapshot(include_histograms=True)
    assert snap["frontier_binding"] == {
        "-:unresolvable": 1,
        "key:signed": 1,
        "key:unresolvable": 2,
        "team:pin_unmatched": 1,
        "team:signed": 1,
    }


def test_record_frontier_binding_helper_tolerates_missing_metrics():
    record_frontier_binding(None, outcome="signed", source="key")
    record_frontier_binding(object(), outcome="signed", source="key")
    metrics = Metrics()
    record_frontier_binding(metrics, outcome="pin_unmatched", source="key")
    assert metrics.snapshot(include_histograms=True)["frontier_binding"] == {
        "key:pin_unmatched": 1
    }


def test_prometheus_emits_frontier_binding_zero_and_labels():
    text = render_prometheus(Metrics())
    assert "# HELP daari_frontier_binding_total" in text
    assert "# TYPE daari_frontier_binding_total counter" in text
    assert "daari_frontier_binding_total 0" in text

    metrics = Metrics()
    metrics.record_frontier_binding(outcome="signed", source="team")
    metrics.record_frontier_binding(outcome="signed", source="team")
    metrics.record_frontier_binding(outcome="pin_unmatched", source="key")
    metrics.record_frontier_binding(outcome="unresolvable", source="team")
    text = render_prometheus(metrics)
    assert 'daari_frontier_binding_total{source="team",outcome="signed"} 2' in text
    assert 'daari_frontier_binding_total{source="key",outcome="pin_unmatched"} 1' in text
    assert 'daari_frontier_binding_total{source="team",outcome="unresolvable"} 1' in text
    assert "daari_frontier_binding_total 0" not in text


@pytest.mark.asyncio
async def test_pool_counts_signed_and_global_key_does_not_increment():
    metrics = Metrics()
    pool, captured = _pool(metrics)

    await pool.execute(_request(), escalated_from="L3", local_confidence=0.2)
    assert captured[-1] == "sk-global"
    assert metrics.snapshot(include_histograms=True)["frontier_binding"] == {}

    await pool.execute(
        _request(frontier_api_key="sk-team-byok", frontier_api_key_source="team"),
        escalated_from="L3",
        local_confidence=0.2,
    )
    assert captured[-1] == "sk-team-byok"
    await pool.execute(
        _request(frontier_api_key="sk-key-byok", frontier_api_key_source="key"),
        escalated_from="L3",
        local_confidence=0.2,
    )
    assert metrics.snapshot(include_histograms=True)["frontier_binding"] == {
        "key:signed": 1,
        "team:signed": 1,
    }


@pytest.mark.asyncio
async def test_pool_counts_pin_unmatched_and_keeps_502(monkeypatch):
    metrics = Metrics()
    pool, _captured = _pool(metrics)

    with pytest.raises(FrontierBindingError) as excinfo:
        await pool.execute(
            _request(frontier_pool="missing-slot", frontier_pool_source="team"),
            escalated_from="L3",
            local_confidence=0.2,
        )
    assert excinfo.value.status_code == 502

    def boom(_ref):
        raise SecretRefError("gone")

    monkeypatch.setattr("daari.auth.frontier_binding.resolve_secret_ref", boom)
    with pytest.raises(FrontierBindingError, match="unresolvable") as excinfo:
        await pool.execute(
            _request(
                frontier_api_key="secret://env-file/x.env#K",
                frontier_api_key_source="key",
            ),
            escalated_from="L3",
            local_confidence=0.1,
        )
    assert excinfo.value.status_code == 502
    assert metrics.snapshot(include_histograms=True)["frontier_binding"] == {
        "key:unresolvable": 1,
        "team:pin_unmatched": 1,
    }


@pytest.mark.asyncio
async def test_pool_stream_counts_binding_outcomes():
    metrics = Metrics()
    executor = FrontierExecutor(
        base_url="http://primary", default_model="a", api_key="sk-global", provider="primary"
    )

    async def stream(request, *, escalated_from, local_confidence):
        yield {"delta": "hi"}

    executor.stream = stream  # type: ignore[method-assign]
    executor.metrics = metrics
    pool = FrontierPool(
        slots=[ProviderSlot(id="primary", executor=executor, keys=["sk-global"])]
    )
    events = [
        event
        async for event in pool.stream(
            _request(frontier_api_key="sk-byok", frontier_api_key_source="key"),
            escalated_from="L3",
            local_confidence=0.2,
        )
    ]
    assert events
    with pytest.raises(FrontierBindingError):
        async for _ in pool.stream(
            _request(frontier_pool="nope", frontier_pool_source="key"),
            escalated_from="L3",
            local_confidence=0.2,
        ):
            pass
    assert metrics.snapshot(include_histograms=True)["frontier_binding"] == {
        "key:pin_unmatched": 1,
        "key:signed": 1,
    }


@pytest.mark.asyncio
async def test_pool_without_metrics_still_fails_closed():
    pool, _captured = _pool(None)
    with pytest.raises(FrontierBindingError):
        await pool.execute(
            _request(frontier_pool="missing-slot", frontier_pool_source="team"),
            escalated_from="L3",
            local_confidence=0.2,
        )


def test_apply_auth_claims_stamps_binding_sources(tmp_path):
    store = VirtualKeyStore(tmp_path / "vk.sqlite3")
    store.create_team("eng")
    created = store.create("alice", team="eng")
    team_claims = AuthClaims(
        kind="virtual",
        key_id=created.key.key_id,
        client_id=created.key.key_id,
        virtual_key=store.resolve(created.plaintext),
        team_frontier_api_key="sk-team",
        team_frontier_pool="team-slot",
    )
    meta = RequestMeta()
    apply_auth_claims_to_meta(meta, team_claims)
    assert meta.frontier_api_key == "sk-team"
    assert meta.frontier_api_key_source == "team"
    assert meta.frontier_pool == "team-slot"
    assert meta.frontier_pool_source == "team"

    # Key credential wins over team; team pool pin still applies.
    store.update_frontier_binding(created.key.key_id, frontier_api_key="sk-key")
    key_claims = AuthClaims(
        kind="virtual",
        key_id=created.key.key_id,
        client_id=created.key.key_id,
        virtual_key=store.resolve(created.plaintext),
        team_frontier_api_key="sk-team",
        team_frontier_pool="team-slot",
    )
    meta = RequestMeta()
    apply_auth_claims_to_meta(meta, key_claims)
    assert meta.frontier_api_key == "sk-key"
    assert meta.frontier_api_key_source == "key"
    assert meta.frontier_pool == "team-slot"
    assert meta.frontier_pool_source == "team"

    unbound = RequestMeta()
    apply_auth_claims_to_meta(
        unbound,
        AuthClaims(kind="virtual", key_id="k", client_id="k", virtual_key=None),
    )
    assert unbound.frontier_api_key is None
    assert unbound.frontier_api_key_source is None
    assert unbound.frontier_pool_source is None


@pytest.mark.asyncio
async def test_stats_exposes_frontier_binding_counters(settings):
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    metrics = app.state.ctx.metrics
    metrics.record_frontier_binding(outcome="signed", source="team")
    metrics.record_frontier_binding(outcome="unresolvable", source="key")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/v1/daari/stats")

    assert response.status_code == 200
    assert response.json()["frontier_binding"] == {
        "key:unresolvable": 1,
        "team:signed": 1,
    }
