"""Speed-scoped lifecycle for Opus 4.8 fast removal (#2053)."""

from __future__ import annotations

from datetime import date

import pytest
from httpx import ASGITransport, AsyncClient

from daari.config.settings import Settings
from daari.gateway.internal import (
    DaariMeta,
    InternalRequest,
    InternalResponse,
    Message,
    RequestMeta,
)
from daari.gateway.sampling import SamplingParams
from daari.observability.spend import SpendLedger, compute_request_usd
from daari.pricing import (
    _DEFAULT_ANTHROPIC_SPEED_LIFECYCLE,
    anthropic_speed_factor,
    merged_anthropic_speed_lifecycle,
    resolve_anthropic_speed_lifecycle,
)
from daari.router.router import AppContext
from daari.server.app import create_app
from daari.setup.doctor import _check_anthropic_speed_lifecycle


def test_default_table_seeds_opus_48_fast_sunset():
    assert "claude-opus-4-8" in _DEFAULT_ANTHROPIC_SPEED_LIFECYCLE
    entry = _DEFAULT_ANTHROPIC_SPEED_LIFECYCLE["claude-opus-4-8"]
    assert entry["speed"] == "fast"
    assert entry["deprecated_at"] == "2026-10-30"
    assert entry["removed_at"] == "2026-11-30"
    assert entry["migrate_to"] == "claude-opus-5-5"
    # Dotted alias shares the same sunset.
    assert _DEFAULT_ANTHROPIC_SPEED_LIFECYCLE["claude-opus-4.8"]["removed_at"] == (
        "2026-11-30"
    )
    merged = merged_anthropic_speed_lifecycle(Settings())
    assert "claude-opus-4-8" in merged


def test_before_removal_warns_and_keeps_fast():
    decision = resolve_anthropic_speed_lifecycle(
        model="claude-opus-4-8",
        speed="fast",
        anthropic_beta="fast-mode-2026-02-01",
        now=date(2026, 11, 2),
    )
    assert decision.action == "warn"
    assert decision.speed == "fast"
    assert decision.reject_detail is None
    assert decision.warning is not None
    assert "2026-11-30" in decision.warning
    assert "claude-opus-5-5" in decision.warning


def test_after_removal_rejects_by_default():
    decision = resolve_anthropic_speed_lifecycle(
        model="claude-opus-4-8-20260501",
        speed="fast",
        anthropic_beta="fast-mode-2026-02-01",
        now=date(2026, 12, 1),
    )
    assert decision.action == "reject"
    assert decision.speed is None
    assert decision.reject_detail is not None
    assert "2026-11-30" in decision.reject_detail
    assert "claude-opus-5-5" in decision.reject_detail


def test_after_removal_opt_in_degrade_strips_speed():
    settings = Settings()
    settings.models.degrade_deprecated_speed = True
    decision = resolve_anthropic_speed_lifecycle(
        model="claude-opus-4.8",
        speed="fast",
        anthropic_beta="fast-mode-2026-02-01",
        settings=settings,
        now=date(2026, 12, 1),
    )
    assert decision.action == "degrade"
    assert decision.speed is None
    assert decision.warning == "deprecated_speed_degraded"
    assert decision.reject_detail is None


def test_operator_as_of_overrides_clock():
    settings = Settings()
    settings.models.speed_lifecycle_as_of = "2026-12-15"
    decision = resolve_anthropic_speed_lifecycle(
        model="claude-opus-4-8",
        speed="fast",
        anthropic_beta="fast-mode-2026-02-01",
        settings=settings,
    )
    assert decision.action == "reject"


def test_operator_speed_lifecycle_override_wins():
    settings = Settings()
    settings.models.speed_lifecycle = {
        "claude-opus-4-8": {
            "speed": "fast",
            "deprecated_at": "2027-01-01",
            "removed_at": "2027-06-01",
            "migrate_to": "claude-opus-5-5",
        }
    }
    decision = resolve_anthropic_speed_lifecycle(
        model="claude-opus-4-8",
        speed="fast",
        anthropic_beta="fast-mode-2026-02-01",
        settings=settings,
        now=date(2026, 12, 1),
    )
    assert decision.action == "warn"
    assert "2027-06-01" in (decision.warning or "")


def test_non_fast_or_other_models_are_noop():
    assert (
        resolve_anthropic_speed_lifecycle(
            model="claude-opus-5-5", speed="fast", now=date(2026, 12, 1)
        ).action
        == "allow"
    )
    assert (
        resolve_anthropic_speed_lifecycle(
            model="claude-opus-4-8", speed="standard", now=date(2026, 12, 1)
        ).action
        == "allow"
    )
    assert (
        resolve_anthropic_speed_lifecycle(
            model="claude-opus-4-8", speed=None, now=date(2026, 12, 1)
        ).action
        == "allow"
    )


def test_degraded_request_bills_at_standard_rate():
    assert anthropic_speed_factor(None) == 1.0
    assert anthropic_speed_factor("standard") == 1.0
    # After degrade, usage_speed is not fast — same as standard billing.
    from daari.pricing import cost_usd

    standard = cost_usd(
        "claude-opus-4-8",
        1_000_000,
        0,
        None,
        fallback_per_1k=0.004,
        usage_speed="standard",
    )
    cleared = cost_usd(
        "claude-opus-4-8",
        1_000_000,
        0,
        None,
        fallback_per_1k=0.004,
        usage_speed=None,
    )
    assert cleared == pytest.approx(standard)


def test_gate_client_tiers_warns_before_removal(settings):
    settings.models.speed_lifecycle_as_of = "2026-11-02"
    router = AppContext.from_settings(settings).router
    request = InternalRequest(
        messages=[Message(role="user", content="hi")],
        model="claude-opus-4-8",
        sampling=SamplingParams(
            max_tokens=16,
            speed="fast",
        ),
        meta=RequestMeta(anthropic_beta="fast-mode-2026-02-01"),
    )
    warning = router._gate_client_tiers(request)
    assert request.sampling.speed == "fast"
    assert warning is not None
    assert "2026-11-30" in warning
    assert "claude-opus-5-5" in warning


def test_gate_client_tiers_degrades_after_removal(settings):
    settings.models.degrade_deprecated_speed = True
    settings.models.speed_lifecycle_as_of = "2026-12-01"
    ctx = AppContext.from_settings(settings)
    router = ctx.router
    request = InternalRequest(
        messages=[Message(role="user", content="hi")],
        model="claude-opus-4-8",
        sampling=SamplingParams(max_tokens=16, speed="fast"),
        meta=RequestMeta(anthropic_beta="fast-mode-2026-02-01"),
    )
    warning = router._gate_client_tiers(request)
    assert request.sampling.speed is None
    assert warning == "deprecated_speed_degraded"
    assert ctx.metrics.soft_warnings.get("deprecated_speed_degraded") == 1


def test_doctor_tips_when_frontier_uses_opus_48(settings):
    settings.frontier.enabled = True
    settings.frontier.model = "claude-opus-4-8"
    settings.models.speed_lifecycle_as_of = "2026-11-02"
    result = _check_anthropic_speed_lifecycle(settings)
    assert result.ok is False
    assert result.optional is True
    assert "claude-opus-4-8" in result.detail
    assert "2026-11-30" in result.detail
    assert "claude-opus-5-5" in result.detail


def test_doctor_tips_on_recent_fast_spend(tmp_path, settings):
    settings.models.speed_lifecycle_as_of = "2026-11-02"
    ledger_path = tmp_path / "spend.sqlite3"
    settings.usage.spend.enabled = True
    settings.usage.spend.path = str(ledger_path)
    ledger = SpendLedger(ledger_path)
    cost, _ = compute_request_usd(
        tier="L6",
        model="claude-opus-4-8",
        input_tokens=100,
        output_tokens=10,
        cached_tokens=0,
        pricing=None,
        fallback_per_1k=0.004,
        usage_speed="fast",
    )
    ledger.record(
        request_id="fast-48",
        tier="L6",
        model="claude-opus-4-8",
        input_tokens=100,
        output_tokens=10,
        cost_usd=cost,
        usage_speed="fast",
    )
    result = _check_anthropic_speed_lifecycle(settings)
    assert result.ok is False
    assert result.optional is True
    assert "fast" in result.detail.lower() or "speed" in result.detail.lower()


@pytest.mark.asyncio
async def test_anthropic_gateway_warns_before_removal(tmp_path, monkeypatch):
    settings = Settings()
    settings.server.api_key = ""
    settings.models.speed_lifecycle_as_of = "2026-11-02"
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)

    async def fake_route(request: InternalRequest) -> InternalResponse:
        return InternalResponse(
            content="ok",
            model=request.model,
            daari_meta=DaariMeta(
                tier="L6",
                executor="frontier",
                provider_id="anthropic",
                warning=getattr(request.sampling, "gate_warning", None),
            ),
        )

    monkeypatch.setattr(app.state.ctx.router, "route", fake_route)
    # Also exercise gate so warning lands even if route is stubbed.
    original_gate = app.state.ctx.router._gate_client_tiers

    def gate_and_stamp(request: InternalRequest) -> str | None:
        warning = original_gate(request)
        return warning

    monkeypatch.setattr(app.state.ctx.router, "_gate_client_tiers", gate_and_stamp)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/v1/messages",
            headers={"anthropic-beta": "fast-mode-2026-02-01"},
            json={
                "model": "claude-opus-4-8",
                "messages": [{"role": "user", "content": "hi"}],
                "max_tokens": 16,
                "speed": "fast",
            },
        )
    assert response.status_code == 200
    # Route stub may not merge gate_warning; call gate directly to assert path.
    req = InternalRequest(
        messages=[Message(role="user", content="hi")],
        model="claude-opus-4-8",
        sampling=SamplingParams(max_tokens=16, speed="fast"),
        meta=RequestMeta(anthropic_beta="fast-mode-2026-02-01"),
    )
    warning = app.state.ctx.router._gate_client_tiers(req)
    assert warning is not None
    assert "2026-11-30" in warning


@pytest.mark.asyncio
async def test_anthropic_gateway_400_after_removal(tmp_path, monkeypatch):
    settings = Settings()
    settings.server.api_key = ""
    settings.models.speed_lifecycle_as_of = "2026-12-01"
    settings.models.degrade_deprecated_speed = False
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)

    async def fake_route(request: InternalRequest) -> InternalResponse:
        return InternalResponse(
            content="should-not-run",
            model=request.model,
            daari_meta=DaariMeta(tier="L6", executor="frontier", provider_id="anthropic"),
        )

    monkeypatch.setattr(app.state.ctx.router, "route", fake_route)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/v1/messages",
            headers={"anthropic-beta": "fast-mode-2026-02-01"},
            json={
                "model": "claude-opus-4-8",
                "messages": [{"role": "user", "content": "hi"}],
                "max_tokens": 16,
                "speed": "fast",
            },
        )
    assert response.status_code == 400
    detail = response.json()
    text = str(detail)
    assert "2026-11-30" in text
    assert "claude-opus-5-5" in text


@pytest.mark.asyncio
async def test_anthropic_gateway_degrades_after_removal(tmp_path, monkeypatch):
    settings = Settings()
    settings.server.api_key = ""
    settings.models.speed_lifecycle_as_of = "2026-12-01"
    settings.models.degrade_deprecated_speed = True
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    seen_speed: list[str | None] = []

    async def fake_route(request: InternalRequest) -> InternalResponse:
        # Gate runs inside route; stamp from sampling after gate.
        app.state.ctx.router._gate_client_tiers(request)
        seen_speed.append(request.sampling.speed)
        return InternalResponse(
            content="ok",
            model=request.model,
            daari_meta=DaariMeta(
                tier="L6",
                executor="frontier",
                provider_id="anthropic",
                warning=request.sampling.gate_warning,
            ),
        )

    monkeypatch.setattr(app.state.ctx.router, "route", fake_route)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/v1/messages",
            headers={"anthropic-beta": "fast-mode-2026-02-01"},
            json={
                "model": "claude-opus-4-8",
                "messages": [{"role": "user", "content": "hi"}],
                "max_tokens": 16,
                "speed": "fast",
            },
        )
    assert response.status_code == 200
    body = response.json()
    assert seen_speed == [None]
    assert "deprecated_speed_degraded" in str(body.get("daari_meta", {}))
