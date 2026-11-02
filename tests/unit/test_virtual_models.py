"""Named virtual models with ordered local/L6 failover (#2023)."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError

from daari.config.settings import RoutingSettings
from daari.gateway.internal import DaariMeta, InternalRequest, InternalResponse
from daari.observability.metrics import Metrics
from daari.router.local_pool import BackendUnavailable
from daari.router.router import AppContext
from daari.router.virtual_models import (
    classify_candidate,
    resolve_virtual_candidates,
    virtual_models_findings,
)
from daari.server.app import create_app
from daari.setup.doctor import _check_virtual_models, run_doctor
from tests.conftest import META_HEADERS


def test_empty_map_leaves_resolve_unchanged():
    assert resolve_virtual_candidates("chat-default", {}) is None
    assert resolve_virtual_candidates("chat-default", None) is None


def test_resolve_order_and_nonempty():
    mapping = {
        "chat-default": ["L3", "L5", "L6"],
        "empty-bad": [],
    }
    assert resolve_virtual_candidates("chat-default", mapping) == ["L3", "L5", "L6"]
    assert resolve_virtual_candidates("missing", mapping) is None
    assert resolve_virtual_candidates("empty-bad", mapping) is None


def test_settings_default_empty_and_rejects_empty_list():
    routing = RoutingSettings()
    assert routing.virtual_models == {}
    with pytest.raises(ValidationError):
        RoutingSettings(virtual_models={"bad": []})


def test_classify_local_tiers_and_frontier(settings):
    assert classify_candidate("L3", settings) == ("local", "L3")
    assert classify_candidate("l5", settings) == ("local", "L5")
    assert classify_candidate(settings.models.l4, settings) == ("local", "L4")
    assert classify_candidate("L6", settings) == ("frontier", "L6")
    assert classify_candidate("openai/gpt-4o-mini", settings) == (
        "frontier",
        "openai/gpt-4o-mini",
    )


def test_findings_empty_and_unknown(settings):
    settings.routing.virtual_models = {
        "ok": ["L3", "L6"],
        "weird": ["totally-unknown-model-xyz"],
    }
    findings = virtual_models_findings(settings)
    assert any("weird" in f and "unknown" in f.lower() for f in findings)
    assert not any("virtual_models['ok']" in f or 'virtual_models["ok"]' in f for f in findings)


@pytest.mark.asyncio
async def test_stop_on_success_skips_later_candidates(settings, monkeypatch):
    settings.routing.virtual_models = {"chat-default": ["L3", "L4", "L6"]}
    settings.cache.l0.enabled = False
    settings.cache.l1.enabled = False
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    calls: list[str] = []

    async def fake_l3(request: InternalRequest) -> InternalResponse:
        calls.append("L3")
        return InternalResponse(
            content="from-l3",
            model=settings.models.l3,
            daari_meta=DaariMeta(tier="L3", executor="ollama", provider_id="ollama"),
        )

    async def boom(request: InternalRequest) -> InternalResponse:
        calls.append("L4")
        raise AssertionError("L4 must not run after L3 success")

    monkeypatch.setattr(app.state.ctx.router.ollama_l3, "execute", fake_l3)
    monkeypatch.setattr(app.state.ctx.router.ollama_l4, "execute", boom)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/chat/completions",
            json={
                "model": "chat-default",
                "messages": [{"role": "user", "content": "hello virtual"}],
            },
            headers=META_HEADERS,
        )
    assert response.status_code == 200
    body = response.json()
    assert body["daari_meta"]["tier"] == "L3"
    assert body["daari_meta"]["virtual_model"] == "chat-default"
    assert body["daari_meta"]["virtual_candidate"] == "L3"
    assert calls == ["L3"]
    assert app.state.ctx.metrics.virtual_model_failover == 0


@pytest.mark.asyncio
async def test_failover_on_backend_unavailable_then_local(settings, monkeypatch):
    settings.routing.virtual_models = {"chat-default": ["L3", "L4"]}
    settings.cache.l0.enabled = False
    settings.cache.l1.enabled = False
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)

    async def fail_l3(request: InternalRequest) -> InternalResponse:
        raise BackendUnavailable("L3", "circuit open")

    async def ok_l4(request: InternalRequest) -> InternalResponse:
        return InternalResponse(
            content="from-l4",
            model=settings.models.l4,
            daari_meta=DaariMeta(tier="L4", executor="ollama", provider_id="ollama"),
        )

    monkeypatch.setattr(app.state.ctx.router.ollama_l3, "execute", fail_l3)
    monkeypatch.setattr(app.state.ctx.router.ollama_l4, "execute", ok_l4)
    # Without a pool, _run_model_tier calls executor directly — raise via wrapper.
    original_run = app.state.ctx.router._run_model_tier

    async def run_with_fail(tier: str, request: InternalRequest):
        if tier == "L3":
            raise BackendUnavailable("L3", "circuit open")
        return await original_run(tier, request)

    monkeypatch.setattr(app.state.ctx.router, "_run_model_tier", run_with_fail)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/chat/completions",
            json={
                "model": "chat-default",
                "messages": [{"role": "user", "content": "failover please"}],
            },
            headers=META_HEADERS,
        )
    assert response.status_code == 200
    body = response.json()
    assert body["daari_meta"]["tier"] == "L4"
    assert body["daari_meta"]["virtual_model"] == "chat-default"
    assert body["daari_meta"]["virtual_candidate"] == "L4"
    assert app.state.ctx.metrics.virtual_model_failover == 1


@pytest.mark.asyncio
async def test_frontier_candidate_respects_no_frontier(settings, monkeypatch):
    settings.routing.virtual_models = {"chat-default": ["L6"]}
    settings.frontier.enabled = True
    settings.cache.l0.enabled = False
    settings.cache.l1.enabled = False
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)

    called = False

    async def fake_l6(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("L6 must not run when no_frontier")

    monkeypatch.setattr(app.state.ctx.router.frontier, "execute", fake_l6)
    original_route = app.state.ctx.router.route

    async def route_no_frontier(request, *args, **kwargs):
        request.meta.no_frontier = True
        return await original_route(request, *args, **kwargs)

    monkeypatch.setattr(app.state.ctx.router, "route", route_no_frontier)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/chat/completions",
            json={
                "model": "chat-default",
                "messages": [{"role": "user", "content": "no cloud"}],
            },
            headers=META_HEADERS,
        )
    assert response.status_code == 503
    assert called is False


@pytest.mark.asyncio
async def test_frontier_candidate_serves_after_local_fail(settings, monkeypatch):
    settings.routing.virtual_models = {"chat-default": ["L3", "openai/gpt-4o-mini"]}
    settings.frontier.enabled = True
    settings.cache.l0.enabled = False
    settings.cache.l1.enabled = False
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)

    async def run_fail(tier: str, request: InternalRequest):
        raise BackendUnavailable(tier, "down")

    monkeypatch.setattr(app.state.ctx.router, "_run_model_tier", run_fail)

    async def fake_l6(request, *, escalated_from: str, local_confidence: float):
        assert request.model == "openai/gpt-4o-mini"
        return InternalResponse(
            content="from-frontier",
            model="openai/gpt-4o-mini",
            daari_meta=DaariMeta(
                tier="L6",
                executor="frontier",
                provider_id="openai",
                escalated_from=escalated_from,
                confidence=local_confidence,
            ),
        )

    monkeypatch.setattr(app.state.ctx.router.frontier, "execute", fake_l6)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/chat/completions",
            json={
                "model": "chat-default",
                "messages": [{"role": "user", "content": "need frontier"}],
            },
            headers=META_HEADERS,
        )
    assert response.status_code == 200
    body = response.json()
    assert body["daari_meta"]["tier"] == "L6"
    assert body["daari_meta"]["virtual_model"] == "chat-default"
    assert body["daari_meta"]["virtual_candidate"] == "openai/gpt-4o-mini"
    assert app.state.ctx.metrics.virtual_model_failover == 1


def test_doctor_warns_on_unknown(settings):
    settings.routing.virtual_models = {"chat-default": ["nope-model"]}
    result = _check_virtual_models(settings)
    assert result.ok is False
    assert result.optional is True
    assert "nope-model" in result.detail or "unknown" in result.detail.lower()


def test_doctor_quiet_when_empty(settings):
    settings.routing.virtual_models = {}
    result = _check_virtual_models(settings)
    assert result.ok is True


def test_run_doctor_includes_virtual_models(settings):
    import httpx

    settings.routing.virtual_models = {"x": ["mystery"]}

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down", request=request)

    results = run_doctor(settings, httpx_client=httpx.Client(transport=httpx.MockTransport(handler)))
    by_name = {r.name: r for r in results}
    assert "virtual_models" in by_name
    assert by_name["virtual_models"].ok is False


def test_metrics_record_virtual_model_failover():
    metrics = Metrics()
    metrics.record_virtual_model_failover()
    metrics.record_virtual_model_failover()
    assert metrics.virtual_model_failover == 2
    snap = metrics.snapshot(include_histograms=True)
    assert snap["virtual_model_failover"] == 2


# --- performance-aware selection (#2052) ---


def test_virtual_model_selection_default_ordered():
    routing = RoutingSettings()
    assert routing.virtual_model_selection == "ordered"


def test_virtual_model_selection_rejects_unknown():
    with pytest.raises(ValidationError):
        RoutingSettings(virtual_model_selection="random")


def test_ewma_erroring_candidate_loses_then_recovers():
    from daari.router.virtual_models import (
        VirtualModelPerformanceTracker,
        order_virtual_candidates,
    )

    tracker = VirtualModelPerformanceTracker(alpha=0.5)
    ordered = ["slow", "fast"]
    # Cold: preserve config order.
    assert order_virtual_candidates(
        ordered, mode="performance", virtual_model="chat", tracker=tracker
    ) == ["slow", "fast"]

    for _ in range(5):
        tracker.observe_error("chat", "slow")
        tracker.observe_success("chat", "fast", latency_ms=50.0)

    ranked = order_virtual_candidates(
        ordered, mode="performance", virtual_model="chat", tracker=tracker
    )
    assert ranked[0] == "fast"
    assert ranked[1] == "slow"

    for _ in range(20):
        tracker.observe_success("chat", "slow", latency_ms=40.0)

    recovered = order_virtual_candidates(
        ordered, mode="performance", virtual_model="chat", tracker=tracker
    )
    assert recovered[0] == "slow"


def test_order_mode_untouched_by_tracker():
    from daari.router.virtual_models import (
        VirtualModelPerformanceTracker,
        order_virtual_candidates,
    )

    tracker = VirtualModelPerformanceTracker()
    tracker.observe_error("chat", "L3")
    tracker.observe_success("chat", "L4", latency_ms=10.0)
    assert order_virtual_candidates(
        ["L3", "L4", "L6"],
        mode="ordered",
        virtual_model="chat",
        tracker=tracker,
    ) == ["L3", "L4", "L6"]


def test_breaker_open_candidates_skipped_in_order():
    from daari.router.virtual_models import order_virtual_candidates

    result = order_virtual_candidates(
        ["L3", "L4", "L5"],
        mode="ordered",
        virtual_model="chat",
        tracker=None,
        breaker_open=lambda c: c == "L3",
    )
    assert result == ["L4", "L5"]


def test_metrics_record_virtual_model_selection_by_mode():
    from daari.observability.prometheus import render_prometheus

    metrics = Metrics()
    metrics.record_virtual_model_selection("ordered")
    metrics.record_virtual_model_selection("performance")
    metrics.record_virtual_model_selection("performance")
    snap = metrics.snapshot(include_histograms=True)
    assert snap["virtual_model_selection"]["ordered"] == 1
    assert snap["virtual_model_selection"]["performance"] == 2
    assert snap["virtual_model_failover"] == 0
    text = render_prometheus(metrics)
    assert 'daari_virtual_model_selection_total{mode="ordered"} 1' in text
    assert 'daari_virtual_model_selection_total{mode="performance"} 2' in text
    assert "daari_virtual_model_failover_total 0" in text


def test_performance_tracker_snapshot_shape():
    from daari.router.virtual_models import VirtualModelPerformanceTracker

    tracker = VirtualModelPerformanceTracker()
    tracker.observe_success("chat", "L3", latency_ms=100.0)
    tracker.observe_error("chat", "L4")
    snap = tracker.snapshot()
    assert "chat" in snap
    assert "L3" in snap["chat"]
    assert snap["chat"]["L3"]["latency_ms"] == pytest.approx(100.0)
    assert snap["chat"]["L3"]["error_rate"] == pytest.approx(0.0)
    assert snap["chat"]["L4"]["error_rate"] > 0


@pytest.mark.asyncio
async def test_performance_mode_prefers_healthy_candidate(settings, monkeypatch):
    settings.routing.virtual_models = {"chat-default": ["L3", "L4"]}
    settings.routing.virtual_model_selection = "performance"
    settings.cache.l0.enabled = False
    settings.cache.l1.enabled = False
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)

    tracker = app.state.ctx.router.virtual_model_perf
    for _ in range(5):
        tracker.observe_error("chat-default", "L3")
        tracker.observe_success("chat-default", "L4", latency_ms=40.0)

    calls: list[str] = []

    async def run_tier(tier: str, request: InternalRequest):
        calls.append(tier)
        return InternalResponse(
            content=f"from-{tier}",
            model=getattr(settings.models, tier.lower()),
            daari_meta=DaariMeta(tier=tier, executor="ollama", provider_id="ollama"),
        )

    monkeypatch.setattr(app.state.ctx.router, "_run_model_tier", run_tier)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/chat/completions",
            json={
                "model": "chat-default",
                "messages": [{"role": "user", "content": "prefer healthy"}],
            },
            headers=META_HEADERS,
        )
    assert response.status_code == 200
    body = response.json()
    assert body["daari_meta"]["virtual_candidate"] == "L4"
    assert calls == ["L4"]
    assert app.state.ctx.metrics.virtual_model_selection.get("performance", 0) >= 1


@pytest.mark.asyncio
async def test_ordered_mode_still_tries_first_candidate(settings, monkeypatch):
    settings.routing.virtual_models = {"chat-default": ["L3", "L4"]}
    settings.routing.virtual_model_selection = "ordered"
    settings.cache.l0.enabled = False
    settings.cache.l1.enabled = False
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)

    tracker = app.state.ctx.router.virtual_model_perf
    for _ in range(5):
        tracker.observe_error("chat-default", "L3")
        tracker.observe_success("chat-default", "L4", latency_ms=40.0)

    calls: list[str] = []

    async def run_tier(tier: str, request: InternalRequest):
        calls.append(tier)
        return InternalResponse(
            content=f"from-{tier}",
            model=getattr(settings.models, tier.lower()),
            daari_meta=DaariMeta(tier=tier, executor="ollama", provider_id="ollama"),
        )

    monkeypatch.setattr(app.state.ctx.router, "_run_model_tier", run_tier)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/chat/completions",
            json={
                "model": "chat-default",
                "messages": [{"role": "user", "content": "ordered first"}],
            },
            headers=META_HEADERS,
        )
    assert response.status_code == 200
    assert response.json()["daari_meta"]["virtual_candidate"] == "L3"
    assert calls == ["L3"]
    assert app.state.ctx.metrics.virtual_model_selection.get("ordered", 0) >= 1
