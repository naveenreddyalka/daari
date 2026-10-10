"""OpenAI-shaped /v1/models lifecycle + server_tools and retired routing (#1521)."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from daari.config.settings import Settings
from daari.gateway.internal import DaariMeta, InternalRequest, InternalResponse, Message
from daari.router.capabilities import (
    anthropic_server_tools,
    openai_model_cards,
    openai_models_payload,
)
from daari.router.router import AppContext
from daari.server.app import create_app


def _settings_with_lifecycle(**overrides: object) -> Settings:
    models: dict[str, object] = {
        "lifecycle": {
            "llama3.2:3b": {
                "lifecycle": "deprecated",
                "deprecated_at": "2026-01-01T00:00:00Z",
                "retires_at": "2026-12-01T00:00:00Z",
            },
            "retired-model": {"lifecycle": "retired"},
        },
        "reject_retired": True,
    }
    models.update(overrides)
    return Settings.model_validate(
        {
            "models": models,
            "frontier": {
                "enabled": True,
                "providers": [
                    {"id": "anthropic", "model": "claude-sonnet-5-5"},
                    {"id": "local", "model": "retired-model"},
                ],
            },
        }
    )


def test_openai_model_cards_include_lifecycle_and_server_tools():
    settings = _settings_with_lifecycle()
    cards = openai_model_cards(settings)
    assert cards
    by_id = {c["id"]: c for c in cards}
    for card in cards:
        assert card["lifecycle"] in ("active", "deprecated", "retired")
        assert "deprecated_at" in card
        assert "retires_at" in card
        assert card["server_tools"] == anthropic_server_tools(card["id"])
        # OpenAI capability tags stay a list.
        assert isinstance(card["capabilities"], list)

    dep = by_id["llama3.2:3b"]
    assert dep["lifecycle"] == "deprecated"
    assert dep["deprecated_at"] == "2026-01-01T00:00:00Z"
    assert dep["retires_at"] == "2026-12-01T00:00:00Z"

    retired = by_id["retired-model"]
    assert retired["lifecycle"] == "retired"

    claude = by_id["claude-sonnet-5-5"]
    assert claude["server_tools"]["supported"] is True
    assert claude["server_tools"]["web_search"]["supported"] is True

    local = by_id["daari"]
    assert local["server_tools"]["supported"] is False


def test_openai_models_payload_lifecycle_filter_default_omits_retired():
    settings = _settings_with_lifecycle()
    default_ids = {c["id"] for c in openai_models_payload(settings)["data"]}
    all_cards = openai_model_cards(settings)
    assert "retired-model" not in default_ids
    assert default_ids == {
        c["id"] for c in all_cards if c["lifecycle"] in ("active", "deprecated")
    }
    retired_only = openai_models_payload(settings, lifecycle="retired")
    assert {c["id"] for c in retired_only["data"]} == {"retired-model"}
    multi = openai_models_payload(settings, lifecycle=["active", "retired"])
    multi_ids = {c["id"] for c in multi["data"]}
    assert "retired-model" in multi_ids
    assert any(c["lifecycle"] == "active" for c in multi["data"])


@pytest.mark.asyncio
async def test_openai_models_http_lifecycle_filter_and_retrieve(settings):
    configured = _settings_with_lifecycle()
    app = create_app(configured)
    app.state.ctx = AppContext.from_settings(configured)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        default = await client.get("/v1/models")
        assert default.status_code == 200
        assert default.json()["object"] == "list"
        default_ids = {c["id"] for c in default.json()["data"]}
        assert "retired-model" not in default_ids
        sample = next(c for c in default.json()["data"] if c["id"] == "llama3.2:3b")
        assert sample["lifecycle"] == "deprecated"
        assert "server_tools" in sample

        with_retired = await client.get("/v1/models", params={"lifecycle": "retired"})
        assert with_retired.status_code == 200
        assert {c["id"] for c in with_retired.json()["data"]} == {"retired-model"}

        retrieved = await client.get("/v1/models/llama3.2:3b")
        assert retrieved.status_code == 200
        body = retrieved.json()
        assert body["object"] == "model"
        assert body["lifecycle"] == "deprecated"
        assert body["server_tools"] == anthropic_server_tools("llama3.2:3b")


@pytest.mark.asyncio
async def test_chat_rejects_retired_model_fail_closed(monkeypatch):
    configured = _settings_with_lifecycle()
    app = create_app(configured)
    app.state.ctx = AppContext.from_settings(configured)
    routed = False

    async def fake_route(request: InternalRequest) -> InternalResponse:
        nonlocal routed
        routed = True
        return InternalResponse(
            content="should not run",
            model=request.model,
            daari_meta=DaariMeta(tier="L3", executor="ollama", provider_id="ollama"),
        )

    monkeypatch.setattr(app.state.ctx.router, "route", fake_route)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/v1/chat/completions",
            json={
                "model": "retired-model",
                "messages": [{"role": "user", "content": "hi"}],
            },
        )
    assert response.status_code == 410
    err = response.json()["error"]
    assert err["type"] == "model_retired"
    assert err["code"] == "model_retired"
    assert routed is False


@pytest.mark.asyncio
async def test_chat_allows_retired_when_reject_retired_false(monkeypatch):
    configured = _settings_with_lifecycle(reject_retired=False)
    app = create_app(configured)
    app.state.ctx = AppContext.from_settings(configured)

    async def fake_route(request: InternalRequest) -> InternalResponse:
        return InternalResponse(
            content="ok",
            model=request.model,
            daari_meta=DaariMeta(tier="L3", executor="ollama", provider_id="ollama"),
        )

    monkeypatch.setattr(app.state.ctx.router, "route", fake_route)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/v1/chat/completions",
            json={
                "model": "retired-model",
                "messages": [{"role": "user", "content": "hi"}],
            },
        )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_deprecated_model_attaches_daari_meta_warning(tmp_path):
    from daari.cache.exact import ExactCache
    from daari.cache.semantic import SemanticCache
    from daari.observability.metrics import Metrics
    from daari.router.router import OllamaExecutor, Router
    from tests.conftest import NoopEmbedder

    executor = OllamaExecutor(
        base_url="http://test", default_model="llama3.2:3b", tier="L3"
    )

    async def fake_execute(request: InternalRequest) -> InternalResponse:
        return InternalResponse(
            content="A confident answer with plenty of length to avoid escalation.",
            model="llama3.2:3b",
            daari_meta=DaariMeta(
                tier="L3", executor="ollama", provider_id="ollama", latency_ms=1
            ),
        )

    executor.execute = fake_execute  # type: ignore[method-assign]
    router = Router(
        cache=ExactCache(str(tmp_path / "l0"), enabled=False),
        semantic_cache=SemanticCache(
            path=str(tmp_path / "l1"), embedder=NoopEmbedder(), enabled=False
        ),
        ollama_l3=executor,
        metrics=Metrics(),
        max_tier_for_chat="L3",
        models_lifecycle={
            "llama3.2:3b": {
                "lifecycle": "deprecated",
                "deprecated_at": "2026-01-01T00:00:00Z",
            }
        },
    )
    response = await router.route(
        InternalRequest(
            messages=[Message(role="user", content="hello there")],
            model="llama3.2:3b",
        )
    )
    assert response.daari_meta.warning == "model_deprecated"


def test_reject_retired_defaults_true():
    settings = Settings()
    assert settings.models.reject_retired is True
    assert settings.models.lifecycle == {}
