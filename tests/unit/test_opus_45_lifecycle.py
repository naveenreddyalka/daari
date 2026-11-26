"""Claude Opus 4.5 deprecation lifecycle: retires 2027-01-22, successor Opus 5.5 (#2439)."""

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
    anthropic_model_cards,
    openai_lifecycle_fields,
    openai_model_cards,
)
from daari.router.router import AppContext
from daari.server.app import create_app
from daari.setup.doctor import _check_model_lifecycle

OPUS_45_IDS = ("claude-opus-4-5", "claude-opus-4-5-20251101")
# OpenAI-shaped facades only echo daari_meta when the client opts in.
META_HEADER = {"X-Daari-Meta": "1"}


def _settings(*, as_of: str, **frontier: object) -> Settings:
    payload: dict[str, object] = {"models": {"lifecycle_as_of": as_of}}
    if frontier:
        payload["frontier"] = frontier
    settings = Settings.model_validate(payload)
    settings.server.api_key = ""
    settings.server.dangerously_permit_weak_or_unset_api_key = True
    return settings


@pytest.mark.parametrize("model_id", OPUS_45_IDS)
def test_default_lifecycle_pins_opus_45_window(model_id):
    entry = _DEFAULT_MODEL_LIFECYCLE[model_id]
    assert entry["lifecycle"] == "deprecated"
    assert entry["deprecated_at"] == "2026-11-23"
    assert entry["retires_at"] == "2027-01-22"
    assert entry["migrate_to"] == "claude-opus-5-5"
    assert model_id in merged_model_lifecycle(Settings())


def test_operator_override_still_wins_for_opus_45():
    settings = Settings.model_validate(
        {"models": {"lifecycle": {"claude-opus-4-5": {"lifecycle": "active"}}}}
    )
    assert anthropic_lifecycle_fields("claude-opus-4-5", settings)["lifecycle"] == "active"
    # The dated id keeps its own shipped row.
    assert (
        anthropic_lifecycle_fields("claude-opus-4-5-20251101", settings)["lifecycle"]
        == "deprecated"
    )


@pytest.mark.parametrize("model_id", OPUS_45_IDS)
def test_lifecycle_fields_deprecated_before_retirement(model_id):
    settings = _settings(as_of="2026-12-01")
    fields = anthropic_lifecycle_fields(model_id, settings)
    assert fields["lifecycle"] == "deprecated"
    assert fields["deprecated_at"] == "2026-11-23"
    assert fields["retires_at"] == "2027-01-22"
    assert fields["migrate_to"] == "claude-opus-5-5"
    openai_fields = openai_lifecycle_fields(model_id, settings)
    assert openai_fields["shutdown_date"] == "2027-01-22"
    assert openai_fields["migrate_to"] == "claude-opus-5-5"


def test_lifecycle_fields_omit_migrate_to_when_unset():
    settings = _settings(as_of="2026-12-01")
    fields = anthropic_lifecycle_fields("gpt-4o-mini", settings)
    assert fields["lifecycle"] == "deprecated"
    assert "migrate_to" not in fields
    assert "migrate_to" not in anthropic_lifecycle_fields("gpt-6-luna", settings)


@pytest.mark.parametrize("as_of", ["2027-01-22", "2027-03-01"])
def test_lifecycle_fields_retired_on_or_after_cutover(as_of):
    settings = _settings(as_of=as_of)
    for model_id in OPUS_45_IDS:
        assert anthropic_lifecycle_fields(model_id, settings)["lifecycle"] == "retired"


def test_lifecycle_as_of_defaults_to_host_clock():
    settings = Settings()
    assert settings.models.lifecycle_as_of is None
    # Shipped already-retired OpenAI id still reads retired without a clock.
    assert anthropic_lifecycle_fields("chatgpt-4o-latest", settings)["lifecycle"] == "retired"


def test_malformed_lifecycle_as_of_falls_back_to_host_clock():
    settings = _settings(as_of="not-a-date")
    # chatgpt-4o-latest is retired explicitly, so this must not raise.
    assert anthropic_lifecycle_fields("chatgpt-4o-latest", settings)["lifecycle"] == "retired"


def test_models_listing_surfaces_opus_45_deprecation_and_shutdown():
    settings = _settings(
        as_of="2026-12-01",
        enabled=True,
        providers=[
            {"id": "anthropic", "model": "claude-opus-4-5"},
            {"id": "anthropic-dated", "model": "claude-opus-4-5-20251101"},
        ],
    )
    openai_cards = {c["id"]: c for c in openai_model_cards(settings)}
    anthropic_cards = {c["id"]: c for c in anthropic_model_cards(settings)}
    for model_id in OPUS_45_IDS:
        card = openai_cards[model_id]
        assert card["lifecycle"] == "deprecated"
        assert card["shutdown_date"] == "2027-01-22"
        assert card["migrate_to"] == "claude-opus-5-5"
        row = anthropic_cards[model_id]
        assert row["lifecycle"] == "deprecated"
        assert row["retires_at"] == "2027-01-22"
        assert row["migrate_to"] == "claude-opus-5-5"


@pytest.mark.asyncio
async def test_models_endpoint_lists_opus_45_as_deprecated():
    settings = _settings(
        as_of="2026-12-01",
        enabled=True,
        providers=[{"id": "anthropic", "model": "claude-opus-4-5", "api_key": "sk-test"}],
    )
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/v1/models")
    assert response.status_code == 200
    by_id = {c["id"]: c for c in response.json()["data"]}
    card = by_id["claude-opus-4-5"]
    assert card["lifecycle"] == "deprecated"
    assert card["shutdown_date"] == "2027-01-22"
    assert card["migrate_to"] == "claude-opus-5-5"


def _warning_stub(app):
    router = app.state.ctx.router

    async def fake_route(request: InternalRequest) -> InternalResponse:
        response = InternalResponse(
            content="ok",
            model=request.model,
            daari_meta=DaariMeta(tier="L6", executor="frontier", provider_id="anthropic"),
        )
        router._apply_lifecycle_warning(request, response)
        return response

    return fake_route


def _frontier_settings(as_of: str) -> Settings:
    return _settings(
        as_of=as_of,
        enabled=True,
        providers=[{"id": "anthropic", "model": "claude-opus-4-5", "api_key": "sk-test"}],
    )


def test_router_warns_on_shipped_deprecated_without_operator_map():
    settings = _frontier_settings("2026-12-01")
    router = AppContext.from_settings(settings).router
    assert router.models_lifecycle == {}
    request = InternalRequest(
        messages=[{"role": "user", "content": "hi"}],
        model="claude-opus-4-5-20251101",
    )
    response = InternalResponse(
        content="ok",
        model=request.model,
        daari_meta=DaariMeta(tier="L6", executor="frontier", provider_id="anthropic"),
    )
    router._apply_lifecycle_warning(request, response)
    assert response.daari_meta.warning == "model_deprecated"


def test_router_does_not_warn_after_retirement_clock():
    settings = _frontier_settings("2027-01-22")
    router = AppContext.from_settings(settings).router
    request = InternalRequest(messages=[{"role": "user", "content": "hi"}], model="claude-opus-4-5")
    response = InternalResponse(
        content="ok",
        model=request.model,
        daari_meta=DaariMeta(tier="L6", executor="frontier", provider_id="anthropic"),
    )
    router._apply_lifecycle_warning(request, response)
    assert response.daari_meta.warning is None


@pytest.mark.asyncio
async def test_chat_completions_serve_opus_45_with_deprecated_warning(monkeypatch):
    settings = _frontier_settings("2026-12-01")
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    monkeypatch.setattr(app.state.ctx.router, "route", _warning_stub(app))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/chat/completions",
            headers=META_HEADER,
            json={
                "model": "claude-opus-4-5",
                "messages": [{"role": "user", "content": "hi"}],
            },
        )
    assert response.status_code == 200
    assert "model_deprecated" in response.json()["daari_meta"]["warning"]


@pytest.mark.asyncio
async def test_messages_serve_opus_45_with_deprecated_warning(monkeypatch):
    settings = _frontier_settings("2026-12-01")
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    monkeypatch.setattr(app.state.ctx.router, "route", _warning_stub(app))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/messages",
            json={
                "model": "claude-opus-4-5-20251101",
                "messages": [{"role": "user", "content": "hi"}],
                "max_tokens": 16,
            },
        )
    assert response.status_code == 200
    assert "model_deprecated" in response.json()["daari_meta"]["warning"]


@pytest.mark.asyncio
async def test_responses_serve_opus_45_with_deprecated_warning(monkeypatch):
    settings = _frontier_settings("2026-12-01")
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    monkeypatch.setattr(app.state.ctx.router, "route", _warning_stub(app))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/responses",
            headers=META_HEADER,
            json={"model": "claude-opus-4-5", "input": "hi"},
        )
    assert response.status_code == 200
    assert "model_deprecated" in response.json()["daari_meta"]["warning"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("path", "body"),
    [
        (
            "/v1/chat/completions",
            {"model": "claude-opus-4-5", "messages": [{"role": "user", "content": "hi"}]},
        ),
        (
            "/v1/messages",
            {
                "model": "claude-opus-4-5-20251101",
                "messages": [{"role": "user", "content": "hi"}],
                "max_tokens": 16,
            },
        ),
        ("/v1/responses", {"model": "claude-opus-4-5", "input": "hi"}),
    ],
)
async def test_opus_45_410_after_retirement(monkeypatch, path, body):
    settings = _frontier_settings("2027-01-22")
    assert settings.models.reject_retired is True
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    routed = False

    async def fake_route(request: InternalRequest) -> InternalResponse:
        nonlocal routed
        routed = True
        return InternalResponse(
            content="nope",
            model=request.model,
            daari_meta=DaariMeta(tier="L6", executor="frontier", provider_id="anthropic"),
        )

    monkeypatch.setattr(app.state.ctx.router, "route", fake_route)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(path, json=body)
    assert response.status_code == 410
    assert response.json()["error"]["code"] == "model_retired"
    assert routed is False


@pytest.mark.asyncio
async def test_opus_45_serves_day_before_retirement(monkeypatch):
    settings = _frontier_settings("2027-01-21")
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    monkeypatch.setattr(app.state.ctx.router, "route", _warning_stub(app))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/chat/completions",
            headers=META_HEADER,
            json={
                "model": "claude-opus-4-5",
                "messages": [{"role": "user", "content": "hi"}],
            },
        )
    assert response.status_code == 200
    assert "model_deprecated" in response.json()["daari_meta"]["warning"]


def test_doctor_tips_when_frontier_default_is_opus_45():
    settings = _settings(as_of="2026-12-01", model="claude-opus-4-5")
    result = _check_model_lifecycle(settings)
    assert result.ok is False
    assert result.optional is True
    assert "frontier.model=claude-opus-4-5" in result.detail
    assert "2027-01-22" in result.detail
    assert "claude-opus-5-5" in result.detail


def test_doctor_tips_when_provider_slot_is_dated_opus_45():
    settings = _settings(
        as_of="2026-12-01",
        enabled=True,
        providers=[{"id": "anthropic", "model": "claude-opus-4-5-20251101"}],
    )
    result = _check_model_lifecycle(settings)
    assert result.ok is False
    assert result.optional is True
    assert "frontier.providers[anthropic].model=claude-opus-4-5-20251101" in result.detail
    assert "claude-opus-5-5" in result.detail


def test_doctor_tips_when_pool_backend_is_opus_45():
    settings = Settings.model_validate(
        {
            "models": {"lifecycle_as_of": "2026-12-01"},
            "routing": {
                "local_pool": {
                    "backends": [
                        {
                            "id": "anth",
                            "kind": "openai",
                            "base_url": "http://x",
                            "model": "claude-opus-4-5",
                        }
                    ]
                }
            },
        }
    )
    result = _check_model_lifecycle(settings)
    assert result.ok is False
    assert "routing.local_pool.backends[anth].model=claude-opus-4-5" in result.detail


def test_doctor_errors_when_opus_45_retired():
    settings = _settings(as_of="2027-01-22", model="claude-opus-4-5")
    result = _check_model_lifecycle(settings)
    assert result.ok is False
    assert result.optional is False
    assert "claude-opus-4-5" in result.detail
