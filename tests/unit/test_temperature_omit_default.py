"""Omitted temperature must not inject 0.7 (Ollama 0.40.14 parity, #2102)."""

from __future__ import annotations

import httpx
import pytest
from httpx import ASGITransport, AsyncClient

from daari.cache.exact import cache_key
from daari.gateway.internal import InternalRequest, Message
from daari.gateway.openai import ChatCompletionRequest
from daari.gateway.responses import ResponsesRequest
from daari.router.openai_executor import OpenAICompatExecutor
from daari.router.router import AppContext
from daari.server.app import create_app
from tests.conftest import META_HEADERS, MOCK_MODEL_CONTENT


def test_chat_completion_temperature_defaults_to_none():
    req = ChatCompletionRequest.model_validate(
        {"model": "daari", "messages": [{"role": "user", "content": "hi"}]}
    )
    assert req.temperature is None


def test_chat_completion_keeps_explicit_temperature():
    req = ChatCompletionRequest.model_validate(
        {
            "model": "daari",
            "messages": [{"role": "user", "content": "hi"}],
            "temperature": 0.7,
        }
    )
    assert req.temperature == 0.7


def test_internal_request_temperature_defaults_to_none():
    req = InternalRequest(messages=[Message(role="user", content="hi")], model="m")
    assert req.temperature is None


def test_cache_key_distinguishes_omitted_from_explicit_0_7():
    messages = [Message(role="user", content="hello there")]
    omitted = InternalRequest(messages=messages, model="llama3.2:3b", temperature=None)
    explicit = InternalRequest(messages=messages, model="llama3.2:3b", temperature=0.7)
    assert cache_key(omitted) != cache_key(explicit)


def test_openai_compat_payload_omits_temperature_when_unset():
    executor = OpenAICompatExecutor(base_url="http://local.test/v1", default_model="m", tier="L3")
    req = InternalRequest(messages=[Message(role="user", content="hi")], model="m")
    payload = executor._payload(req, "m", stream=False)
    assert "temperature" not in payload


def test_openai_compat_payload_forwards_explicit_0_7():
    executor = OpenAICompatExecutor(base_url="http://local.test/v1", default_model="m", tier="L3")
    req = InternalRequest(
        messages=[Message(role="user", content="hi")], model="m", temperature=0.7
    )
    payload = executor._payload(req, "m", stream=False)
    assert payload["temperature"] == 0.7


def test_responses_request_temperature_defaults_to_none():
    body = ResponsesRequest.model_validate({"model": "daari", "input": "hi"})
    assert body.temperature is None


def _recording_transport(content: str = MOCK_MODEL_CONTENT):
    bodies: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        import json as _json

        bodies.append(_json.loads(request.content))
        return httpx.Response(200, json={"message": {"content": content}})

    return httpx.MockTransport(handler), bodies


def _patch_transport(monkeypatch, transport):
    real = httpx.AsyncClient

    def factory(*args, **kwargs):
        kwargs["transport"] = transport
        return real(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", factory)


def _app(settings, tmp_path):
    settings.cache.l0.enabled = False
    settings.cache.l1.enabled = False
    settings.routing.max_tier_for_chat = "L3"
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    return app


@pytest.mark.asyncio
async def test_chat_completions_omitted_temperature_absent_on_ollama_wire(
    settings, tmp_path, monkeypatch
):
    transport, bodies = _recording_transport()
    _patch_transport(monkeypatch, transport)
    app = _app(settings, tmp_path)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/chat/completions",
            json={"model": "daari", "messages": [{"role": "user", "content": "hello there"}]},
            headers=META_HEADERS,
        )
    assert response.status_code == 200
    assert "temperature" not in bodies[0].get("options", {})


@pytest.mark.asyncio
async def test_responses_omitted_temperature_absent_on_ollama_wire(
    settings, tmp_path, monkeypatch
):
    transport, bodies = _recording_transport()
    _patch_transport(monkeypatch, transport)
    app = _app(settings, tmp_path)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/responses",
            json={"model": "daari", "input": "hello there"},
            headers=META_HEADERS,
        )
    assert response.status_code == 200, response.text
    assert "temperature" not in bodies[0].get("options", {})


@pytest.mark.asyncio
async def test_responses_explicit_temperature_reaches_openai_compat(settings, tmp_path):
    """Responses path must not re-inject 0.7 when the client set temperature (#2102)."""
    from daari.gateway.internal import InternalRequest as IR

    captured: list[IR] = []

    async def fake_route(request: IR):
        captured.append(request)
        from daari.gateway.internal import DaariMeta, InternalResponse

        return InternalResponse(
            content="ok",
            model=request.model,
            daari_meta=DaariMeta(tier="L3", executor="ollama", latency_ms=1),
        )

    settings.cache.l0.enabled = False
    settings.cache.l1.enabled = False
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    app.state.ctx.router.route = fake_route  # type: ignore[method-assign]

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        omitted = await client.post(
            "/v1/responses",
            json={"model": "daari", "input": "hi"},
            headers=META_HEADERS,
        )
        explicit = await client.post(
            "/v1/responses",
            json={"model": "daari", "input": "hi", "temperature": 0.7},
            headers=META_HEADERS,
        )
    assert omitted.status_code == 200, omitted.text
    assert explicit.status_code == 200, explicit.text
    assert captured[0].temperature is None
    assert captured[1].temperature == 0.7


def test_ollama_docs_mention_sampler_default_parity():
    from pathlib import Path

    text = (
        Path(__file__).resolve().parents[2]
        / "docs/developer/guides/backends/ollama.md"
    ).read_text(encoding="utf-8")
    assert "0.40.14" in text
    assert "temperature" in text.lower()
