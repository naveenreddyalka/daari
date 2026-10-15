"""Shipped OpenAI retirement defaults + shutdown_date (#1653)."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from daari.config.settings import (
    Settings,
    _DEFAULT_MODEL_LIFECYCLE,
    merged_model_lifecycle,
)
from daari.gateway.internal import DaariMeta, InternalRequest, InternalResponse
from daari.router.capabilities import (
    anthropic_lifecycle_fields,
    openai_lifecycle_fields,
    openai_model_cards,
)
from daari.router.router import AppContext
from daari.server.app import create_app
from daari.setup.doctor import _check_model_lifecycle


def test_default_lifecycle_covers_openai_waves():
    assert "gpt-4o" in _DEFAULT_MODEL_LIFECYCLE
    assert "gpt-4o-mini" in _DEFAULT_MODEL_LIFECYCLE
    assert "gpt-4.1" in _DEFAULT_MODEL_LIFECYCLE
    assert "gpt-4-turbo" in _DEFAULT_MODEL_LIFECYCLE
    assert "o1" in _DEFAULT_MODEL_LIFECYCLE
    assert _DEFAULT_MODEL_LIFECYCLE["gpt-4o"]["retires_at"] == "2027-01-14"
    assert _DEFAULT_MODEL_LIFECYCLE["gpt-4-turbo"]["retires_at"] == "2026-10-23"
    assert _DEFAULT_MODEL_LIFECYCLE["chatgpt-4o-latest"]["lifecycle"] == "retired"


def test_operator_lifecycle_overrides_defaults():
    settings = Settings.model_validate(
        {"models": {"lifecycle": {"gpt-4o": {"lifecycle": "active"}}}}
    )
    merged = merged_model_lifecycle(settings)
    assert merged["gpt-4o"]["lifecycle"] == "active"
    assert merged["gpt-4o-mini"]["lifecycle"] == "deprecated"


def test_gpt4o_deprecated_with_shutdown_date():
    settings = Settings()
    fields = openai_lifecycle_fields("gpt-4o-mini", settings)
    assert fields["lifecycle"] == "deprecated"
    assert fields["shutdown_date"] == "2027-01-14"
    assert fields["retires_at"] == "2027-01-14"
    # Anthropic-shaped cards keep retires_at, not shutdown_date.
    anth = anthropic_lifecycle_fields("gpt-4o-mini", settings)
    assert "shutdown_date" not in anth
    assert anth["retires_at"] == "2027-01-14"


def test_openai_model_cards_include_shutdown_date_for_frontier_default():
    settings = Settings.model_validate(
        {
            "frontier": {
                "enabled": True,
                "providers": [{"id": "openai", "model": "gpt-4o-mini"}],
            }
        }
    )
    cards = openai_model_cards(settings)
    by_id = {c["id"]: c for c in cards}
    assert "gpt-4o-mini" in by_id
    assert by_id["gpt-4o-mini"]["shutdown_date"] == "2027-01-14"
    assert by_id["gpt-4o-mini"]["lifecycle"] == "deprecated"


def test_stock_frontier_default_is_current_model():
    settings = Settings()
    assert settings.frontier.model == "gpt-6-luna"
    assert anthropic_lifecycle_fields("gpt-6-luna", settings)["lifecycle"] == "active"


def test_doctor_flags_deprecated_frontier_with_shutdown():
    settings = Settings.model_validate({"frontier": {"model": "gpt-4o-mini"}})
    result = _check_model_lifecycle(settings)
    assert result.ok is False
    assert result.optional is True
    assert "gpt-4o-mini" in result.detail
    assert "2027-01-14" in result.detail


@pytest.mark.asyncio
async def test_retired_default_wave_410_without_operator_config(monkeypatch):
    settings = Settings()
    settings.server.api_key = ""
    settings.server.dangerously_permit_weak_or_unset_api_key = True
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    routed = False

    async def fake_route(request: InternalRequest) -> InternalResponse:
        nonlocal routed
        routed = True
        return InternalResponse(
            content="nope",
            model=request.model,
            daari_meta=DaariMeta(tier="L6", executor="openai", provider_id="openai"),
        )

    monkeypatch.setattr(app.state.ctx.router, "route", fake_route)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/chat/completions",
            json={
                "model": "chatgpt-4o-latest",
                "messages": [{"role": "user", "content": "hi"}],
            },
        )
    assert response.status_code == 410
    assert response.json()["error"]["code"] == "model_retired"
    assert routed is False
