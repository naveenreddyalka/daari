"""Per-model daily rpd/tpd + virtual-model skip-on-exhaust (#2240)."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from daari.auth.rate_limit import MemoryCounterBackend, RateLimiter
from daari.config.settings import ModelRateLimitSettings
from daari.gateway.internal import DaariMeta, InternalRequest, InternalResponse
from daari.router.router import AppContext
from daari.server.app import create_app
from tests.conftest import META_HEADERS


def test_model_rate_limit_settings_accept_rpd_tpd():
    entry = ModelRateLimitSettings(rpm=2, tpm=100, rpd=5, tpd=1000)
    assert entry.rpd == 5
    assert entry.tpd == 1000
    unset = ModelRateLimitSettings()
    assert unset.rpd == 0
    assert unset.tpd == 0


def test_resolve_model_limits_includes_daily():
    limiter = RateLimiter(
        MemoryCounterBackend(),
        model_rpd=10,
        model_tpd=100,
        models={"openai/gpt-4o": ModelRateLimitSettings(rpd=2, tpd=50)},
    )
    assert limiter.resolve_model_limits("openai/gpt-4o") == (0, 0, 0, 2, 50)
    assert limiter.resolve_model_limits("other") == (0, 0, 0, 10, 100)


def test_per_model_rpd_isolates_models(monkeypatch):
    monkeypatch.setattr("daari.auth.rate_limit._wall_time", lambda: 1_700_000_000.0)
    limiter = RateLimiter(
        MemoryCounterBackend(),
        models={
            "noisy": ModelRateLimitSettings(rpd=1),
            "quiet": ModelRateLimitSettings(rpd=1),
        },
    )
    assert limiter.check(key_id="k", model="noisy", tokens=1).allowed
    denied = limiter.check(key_id="k", model="noisy", tokens=1)
    assert not denied.allowed
    assert denied.scope == "rpd"
    assert denied.bucket == "model"
    assert limiter.check(key_id="k", model="quiet", tokens=1).allowed


def test_per_model_tpd_denies_after_token_budget(monkeypatch):
    monkeypatch.setattr("daari.auth.rate_limit._wall_time", lambda: 1_700_000_000.0)
    limiter = RateLimiter(
        MemoryCounterBackend(),
        models={"frontier": ModelRateLimitSettings(tpd=50)},
    )
    assert limiter.check(key_id="k", model="frontier", tokens=40).allowed
    denied = limiter.check(key_id="k", model="frontier", tokens=20)
    assert not denied.allowed
    assert denied.scope == "tpd"
    assert denied.bucket == "model"


def test_global_model_rpd_applies_when_map_unset(monkeypatch):
    monkeypatch.setattr("daari.auth.rate_limit._wall_time", lambda: 1_700_000_000.0)
    limiter = RateLimiter(MemoryCounterBackend(), model_rpd=1)
    assert limiter.check(key_id="k", model="any", tokens=1).allowed
    denied = limiter.check(key_id="k", model="any", tokens=1)
    assert not denied.allowed
    assert denied.bucket == "model"
    assert denied.scope == "rpd"


def test_model_daily_exhausted_peek_does_not_consume(monkeypatch):
    monkeypatch.setattr("daari.auth.rate_limit._wall_time", lambda: 1_700_000_000.0)
    limiter = RateLimiter(
        MemoryCounterBackend(),
        models={"openai/gpt-4o": ModelRateLimitSettings(rpd=1)},
    )
    assert limiter.check(key_id="k", model="openai/gpt-4o", tokens=1).allowed
    assert limiter.model_daily_exhausted(key_id="k", model="openai/gpt-4o", tokens=1)
    # Peek must not burn another unit — still exhausted, not deeper.
    again = limiter.check(key_id="k", model="openai/gpt-4o", tokens=1)
    assert not again.allowed
    assert again.remaining == 0


def test_doctor_tip_frontier_without_daily_cap(settings, tmp_path):
    from daari.setup.doctor import _check_virtual_model_frontier_daily_cap

    settings.routing.virtual_models = {"chat": ["openai/gpt-4o", "L3"]}
    settings.rate_limit.models = {}
    settings.rate_limit.model_rpd = 0
    settings.rate_limit.model_tpd = 0
    settings.server.virtual_keys.path = str(tmp_path / "keys.sqlite3")
    tip = _check_virtual_model_frontier_daily_cap(settings)
    assert tip is not None
    assert tip.ok is True
    assert "daily" in tip.detail.lower() or "rpd" in tip.detail.lower()


def test_doctor_quiet_when_model_daily_set(settings, tmp_path):
    from daari.setup.doctor import _check_virtual_model_frontier_daily_cap

    settings.routing.virtual_models = {"chat": ["openai/gpt-4o", "L3"]}
    settings.rate_limit.models = {
        "openai/gpt-4o": ModelRateLimitSettings(rpd=100),
    }
    settings.server.virtual_keys.path = str(tmp_path / "keys.sqlite3")
    tip = _check_virtual_model_frontier_daily_cap(settings)
    assert tip is None


@pytest.mark.asyncio
async def test_gateway_model_rpd_429_isolates_models(settings, tmp_path, monkeypatch):
    monkeypatch.setattr("daari.auth.rate_limit._wall_time", lambda: 1_700_000_000.0)
    settings.cache.l0.enabled = False
    settings.cache.l1.enabled = False
    settings.rate_limit.models = {
        "noisy": ModelRateLimitSettings(rpd=1),
        "quiet": ModelRateLimitSettings(rpd=10),
    }
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)

    async def ok(_request: InternalRequest) -> InternalResponse:
        return InternalResponse(
            content="ok",
            model="m",
            daari_meta=DaariMeta(tier="L3", executor="ollama", provider_id="ollama"),
        )

    monkeypatch.setattr(app.state.ctx.router.ollama_l3, "execute", ok)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        first = await client.post(
            "/v1/chat/completions",
            json={"model": "noisy", "messages": [{"role": "user", "content": "a"}]},
            headers=META_HEADERS,
        )
        second = await client.post(
            "/v1/chat/completions",
            json={"model": "noisy", "messages": [{"role": "user", "content": "b"}]},
            headers=META_HEADERS,
        )
        other = await client.post(
            "/v1/chat/completions",
            json={"model": "quiet", "messages": [{"role": "user", "content": "c"}]},
            headers=META_HEADERS,
        )
    assert first.status_code == 200
    assert second.status_code == 429
    assert "rpd" in second.json()["error"]["message"]
    assert other.status_code == 200


@pytest.mark.asyncio
async def test_virtual_model_skips_candidate_on_model_daily_exhaust(
    settings, tmp_path, monkeypatch
):
    monkeypatch.setattr("daari.auth.rate_limit._wall_time", lambda: 1_700_000_000.0)
    settings.routing.virtual_models = {"chat-default": ["openai/gpt-4o-mini", "L3"]}
    settings.frontier.enabled = True
    settings.cache.l0.enabled = False
    settings.cache.l1.enabled = False
    settings.rate_limit.models = {
        "openai/gpt-4o-mini": ModelRateLimitSettings(rpd=1),
    }
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    # Wire router limiter the same way create_app lifespan does.
    app.state.ctx.rate_limiter = app.state.rate_limiter
    app.state.ctx.router.rate_limiter = app.state.rate_limiter

    # Exhaust frontier candidate daily quota via direct model checks.
    # Unauthenticated test settings still resolve master Bearer → key_id "master".
    limiter = app.state.rate_limiter
    assert limiter.check(key_id="master", model="openai/gpt-4o-mini", tokens=1).allowed
    assert limiter.model_daily_exhausted(
        key_id="master", model="openai/gpt-4o-mini", tokens=1
    )

    frontier_calls = []

    async def fake_frontier(*args, **kwargs):
        frontier_calls.append(1)
        raise AssertionError("frontier must be skipped when daily quota exhausted")

    async def ok_l3(request: InternalRequest) -> InternalResponse:
        return InternalResponse(
            content="from-l3",
            model=settings.models.l3,
            daari_meta=DaariMeta(tier="L3", executor="ollama", provider_id="ollama"),
        )

    monkeypatch.setattr(app.state.ctx.router.frontier, "execute", fake_frontier)
    monkeypatch.setattr(app.state.ctx.router.ollama_l3, "execute", ok_l3)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/chat/completions",
            json={
                "model": "chat-default",
                "messages": [{"role": "user", "content": "failover please"}],
            },
            headers=META_HEADERS,
        )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body.get("daari_meta", {}).get("tier") == "L3", body
    assert body["daari_meta"]["virtual_candidate"] == "L3"
    assert frontier_calls == []
    metrics = app.state.ctx.metrics
    assert metrics.virtual_model_daily_quota_skip >= 1
    # Distinct from hard 429 reject path.
    assert metrics.rejects.get("rate_limit_rpd", 0) == 0
    assert metrics.virtual_model_failover >= 1


def test_prometheus_exports_daily_quota_skip_counter():
    from daari.observability.metrics import Metrics
    from daari.observability.prometheus import render_prometheus

    metrics = Metrics()
    metrics.record_virtual_model_daily_quota_skip()
    text = render_prometheus(metrics)
    assert "daari_virtual_model_daily_quota_skip_total" in text
    assert "daari_virtual_model_daily_quota_skip_total 1" in text
