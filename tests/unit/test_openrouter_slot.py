"""G3 / #225: first-class OpenRouter L6 slot."""

from __future__ import annotations

import os

import httpx
import pytest

from daari.config.settings import FrontierSettings, Settings
from daari.gateway.internal import InternalRequest, Message
from daari.router.aliases import local_model_alias
from daari.router.frontier import FrontierExecutor
from daari.router.frontier_pool import build_frontier_pool
from daari.router.openrouter import OPENROUTER_BASE_URL, openrouter_headers, openrouter_slot


def test_openrouter_slot_template():
    slot = openrouter_slot()
    assert slot.id == "openrouter"
    assert slot.base_url == OPENROUTER_BASE_URL
    assert slot.model == "openrouter/auto"
    assert slot.api_key_env == "OPENROUTER_API_KEY"


def test_build_pool_from_openrouter_template(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    settings = Settings()
    settings.frontier = FrontierSettings(enabled=True, providers=[openrouter_slot()])
    pool = build_frontier_pool(settings)
    assert pool.slots[0].id == "openrouter"
    assert pool.slots[0].executor.default_model == "openrouter/auto"
    assert "sk-or-test" in pool.slots[0].keys


def test_openrouter_headers_include_attribution():
    headers = openrouter_headers("sk-or-test")
    assert headers["Authorization"] == "Bearer sk-or-test"
    assert headers["HTTP-Referer"]
    assert headers["X-Title"] == "daari"


def test_local_model_aliases():
    assert local_model_alias("daari:floor") == "floor"
    assert local_model_alias("llama3.2:3b:floor") == "floor"
    assert local_model_alias("daari:nitro") == "nitro"
    assert local_model_alias("daari") is None
    assert local_model_alias("openrouter/auto") is None


@pytest.mark.asyncio
async def test_openrouter_execute_sends_referer_and_zero_daari_cost():
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["headers"] = dict(request.headers)
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "or answer"}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 4, "cost": 0.001},
            },
        )

    executor = FrontierExecutor(
        base_url=OPENROUTER_BASE_URL,
        default_model="openrouter/auto",
        api_key="sk-or-test",
        provider="openrouter",
        transport=httpx.MockTransport(handler),
    )
    response = await executor.execute(
        InternalRequest(messages=[Message(role="user", content="hi")], model="daari"),
        escalated_from="L3",
        local_confidence=0.2,
    )
    assert captured["headers"].get("http-referer") or captured["headers"].get("HTTP-Referer")
    assert (captured["headers"].get("x-title") or captured["headers"].get("X-Title")) == "daari"
    assert response.daari_meta.cost_usd == pytest.approx(0.001)
    assert response.daari_meta.daari_cost_usd == 0.0


def test_live_openrouter_gate():
    from daari.router.openrouter import live_openrouter_available

    assert live_openrouter_available() is bool(os.environ.get("OPENROUTER_API_KEY"))


@pytest.mark.integration
@pytest.mark.asyncio
async def test_live_openrouter_chat():
    from daari.router.openrouter import live_openrouter_available

    if not live_openrouter_available():
        pytest.skip("OPENROUTER_API_KEY not set")
    key = os.environ["OPENROUTER_API_KEY"]
    executor = FrontierExecutor(
        base_url=OPENROUTER_BASE_URL,
        default_model="openrouter/auto",
        api_key=key,
        provider="openrouter",
        timeout=30.0,
    )
    response = await executor.execute(
        InternalRequest(
            messages=[Message(role="user", content="Reply with the single word ok.")],
            model="daari",
        ),
        escalated_from="L3",
        local_confidence=0.2,
    )
    assert response.content.strip()
    assert response.daari_meta.daari_cost_usd == 0.0
