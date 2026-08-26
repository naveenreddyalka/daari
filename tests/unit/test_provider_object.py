"""G2 / #224: OpenRouter `provider` object on L6."""

from __future__ import annotations

import json

import httpx
import pytest

from daari.config.settings import FrontierProviderConfig
from daari.gateway.internal import DaariMeta, InternalRequest, Message, RequestMeta
from daari.gateway.openai import ChatCompletionRequest, _prepare_internal_request
from daari.gateway.provider_prefs import (
    ProviderPreferences,
    ZdrUnavailable,
    as_openrouter_payload,
    is_openrouter_base,
    parse_provider,
    require_zdr_slot,
)
from daari.router.frontier import FrontierExecutor
from daari.router.frontier_pool import FrontierPool, ProviderSlot


def test_parse_openrouter_provider_object():
    prefs = parse_provider(
        {
            "zdr": True,
            "sort": "price",
            "order": ["anthropic", "openai"],
            "allow_fallbacks": False,
            "max_price": {"prompt": 1.0, "completion": 2.0},
            "data_collection": "deny",
        }
    )
    assert prefs is not None
    assert prefs.zdr is True
    assert prefs.sort == "price"
    assert prefs.order == ["anthropic", "openai"]
    assert prefs.allow_fallbacks is False
    assert prefs.max_price == {"prompt": 1.0, "completion": 2.0}
    assert prefs.data_collection == "deny"


def test_parse_provider_empty_is_none():
    assert parse_provider(None) is None
    assert parse_provider({}) is None


def test_anthropic_body_keeps_provider():
    from daari.gateway.anthropic import AnthropicRequest

    body = AnthropicRequest.model_validate(
        {
            "model": "claude-sonnet-4-5",
            "max_tokens": 16,
            "messages": [{"role": "user", "content": "hi"}],
            "provider": {"zdr": True, "sort": "price"},
        }
    )
    prefs = parse_provider(body.provider)
    assert prefs is not None
    assert prefs.zdr is True
    assert prefs.sort == "price"


def test_openai_body_keeps_provider_on_internal_request():
    body = ChatCompletionRequest.model_validate(
        {
            "model": "daari",
            "messages": [{"role": "user", "content": "hi"}],
            "provider": {"zdr": True, "sort": "price"},
        }
    )
    req = _prepare_internal_request(body, default_model="llama3.2:3b", meta=RequestMeta())
    assert req.provider is not None
    assert req.provider.zdr is True
    assert req.provider.sort == "price"


def test_as_openrouter_payload_omits_unset():
    payload = as_openrouter_payload(ProviderPreferences(zdr=True, sort="price"))
    assert payload == {"zdr": True, "sort": "price"}


def test_is_openrouter_base():
    assert is_openrouter_base("https://openrouter.ai/api/v1")
    assert not is_openrouter_base("https://api.openai.com/v1")


def test_require_zdr_slot_fails_closed():
    with pytest.raises(ZdrUnavailable, match="zdr"):
        require_zdr_slot(
            ProviderPreferences(zdr=True),
            [FrontierProviderConfig(id="openai", zdr=False)],
        )


def test_require_zdr_slot_ok_when_a_slot_declares_it():
    require_zdr_slot(
        ProviderPreferences(zdr=True, sort="price"),
        [FrontierProviderConfig(id="openrouter", zdr=True)],
    )


def test_require_zdr_slot_noop_without_constraint():
    require_zdr_slot(ProviderPreferences(zdr=False), [])
    require_zdr_slot(None, [])


@pytest.mark.asyncio
async def test_openrouter_execute_passes_provider_and_records_cost():
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "from openrouter"}}],
                "usage": {
                    "prompt_tokens": 80,
                    "completion_tokens": 10,
                    "cost": 0.0042,
                    "prompt_tokens_details": {"cached_tokens": 64},
                },
            },
        )

    executor = FrontierExecutor(
        base_url="https://openrouter.ai/api/v1",
        default_model="openrouter/auto",
        api_key="sk-or-test",
        provider="openrouter",
        transport=httpx.MockTransport(handler),
    )
    request = InternalRequest(
        messages=[Message(role="user", content="hello")],
        model="daari",
        provider=ProviderPreferences(zdr=True, sort="price"),
    )
    response = await executor.execute(request, escalated_from="L3", local_confidence=0.2)
    assert captured["body"]["provider"] == {"zdr": True, "sort": "price"}
    assert response.daari_meta.cost_usd == pytest.approx(0.0042)
    assert response.daari_meta.cached_tokens == 64
    assert response.daari_meta.provider_prefs == {"zdr": True, "sort": "price"}


@pytest.mark.asyncio
async def test_pool_raises_when_zdr_required_and_no_slot():
    executor = FrontierExecutor(
        base_url="https://api.openai.com/v1",
        default_model="gpt-4o-mini",
        api_key="sk-test",
        provider="openai",
    )
    pool = FrontierPool(
        slots=[ProviderSlot(id="openai", executor=executor, keys=["sk-test"], zdr=False)]
    )
    request = InternalRequest(
        messages=[Message(role="user", content="secret")],
        model="daari",
        provider=ProviderPreferences(zdr=True),
    )
    with pytest.raises(ZdrUnavailable):
        await pool.execute(request, escalated_from="L3", local_confidence=0.1)


@pytest.mark.asyncio
async def test_gateway_rejects_zdr_when_no_slot_declares_it(tmp_path, monkeypatch):
    from daari.config.settings import Settings
    from daari.router.router import AppContext
    from daari.server.app import create_app
    from httpx import ASGITransport, AsyncClient
    from tests.conftest import META_HEADERS

    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key")
    settings = Settings.model_validate(
        {
            "server": {"host": "127.0.0.1", "port": 11435},
            "models": {"l3": "llama3.2:3b"},
            "ollama": {"base_url": "http://127.0.0.1:11434"},
            "cache": {
                "l0": {"enabled": False, "path": str(tmp_path / "l0")},
                "l1": {"enabled": False, "path": str(tmp_path / "l1")},
            },
            "frontier": {
                "enabled": True,
                "provider": "openai",
                "model": "gpt-4o-mini",
                "providers": [
                    {
                        "id": "openai",
                        "base_url": "https://api.openai.com/v1",
                        "model": "gpt-4o-mini",
                        "zdr": False,
                    }
                ],
            },
        }
    )
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)

    payload = {
        "model": "daari",
        "messages": [{"role": "user", "content": "classified"}],
        "provider": {"zdr": True, "sort": "price"},
    }
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/v1/chat/completions", json=payload, headers=META_HEADERS)

    assert response.status_code == 400
    detail = response.json().get("detail") or response.text
    assert "zdr" in str(detail).lower()
