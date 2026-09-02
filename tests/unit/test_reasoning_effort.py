"""reasoning_effort is accepted, forwarded, and optionally biases tiers (#297)."""

from __future__ import annotations

import json

import httpx
import pytest
from httpx import ASGITransport, AsyncClient

from daari.gateway.internal import InternalRequest, Message, RequestMeta
from daari.gateway.openai import ChatCompletionRequest, _prepare_internal_request
from daari.gateway.sampling import SamplingParams
from daari.router.profile import build_prompt_profile
from daari.router.router import AppContext, OllamaExecutor, Router
from daari.server.app import create_app
from tests.conftest import META_HEADERS
from tests.unit.test_tier_cap import _router


def test_chat_completion_request_keeps_reasoning_effort():
    body = ChatCompletionRequest.model_validate(
        {
            "model": "daari",
            "messages": [{"role": "user", "content": "hi"}],
            "reasoning_effort": "high",
        }
    )
    req = _prepare_internal_request(body, default_model="llama3.2:3b", meta=RequestMeta())
    assert req.sampling.reasoning_effort == "high"


def test_ollama_payload_sets_think_for_thinking_model():
    executor = OllamaExecutor(base_url="http://127.0.0.1:11434", default_model="gpt-oss:20b")
    request = InternalRequest(
        messages=[Message(role="user", content="plan")],
        model="gpt-oss:20b",
        sampling=SamplingParams(reasoning_effort="high"),
    )
    payload = executor._payload(request, "gpt-oss:20b", stream=False)
    assert payload["think"] == "high"


def test_ollama_payload_omits_think_for_plain_model():
    executor = OllamaExecutor(base_url="http://127.0.0.1:11434", default_model="llama3.2:3b")
    request = InternalRequest(
        messages=[Message(role="user", content="plan")],
        model="llama3.2:3b",
        sampling=SamplingParams(reasoning_effort="high"),
    )
    payload = executor._payload(request, "llama3.2:3b", stream=False)
    assert "think" not in payload


def test_ollama_payload_omits_think_for_minimal():
    executor = OllamaExecutor(base_url="http://127.0.0.1:11434", default_model="gpt-oss:20b")
    request = InternalRequest(
        messages=[Message(role="user", content="hi")],
        model="gpt-oss:20b",
        sampling=SamplingParams(reasoning_effort="minimal"),
    )
    payload = executor._payload(request, "gpt-oss:20b", stream=False)
    assert "think" not in payload


def test_profile_marks_complex_when_escalation_flag_and_high_effort():
    request = InternalRequest(
        messages=[Message(role="user", content="short ask")],
        model="daari",
        sampling=SamplingParams(reasoning_effort="high"),
    )
    plain = build_prompt_profile(request)
    assert plain.complexity != "complex"
    bumped = build_prompt_profile(request, effort_escalation=True)
    assert bumped.complexity == "complex"


def test_high_effort_biases_tier_when_flag_on(tmp_path):
    calls: list[str] = []
    router = _router(tmp_path, calls=calls)
    router.reasoning_effort_escalation = True
    request = InternalRequest(
        messages=[Message(role="user", content="short ask")],
        model="daari",
        sampling=SamplingParams(reasoning_effort="high"),
        meta=RequestMeta(no_cache=True),
    )
    # Without bias, a short prompt is L3; with flag+high, floor is L4.
    assert router._choose_uncapped_tier(request) == "L4"


def test_high_effort_does_not_bias_when_flag_off(tmp_path):
    router = _router(tmp_path)
    router.reasoning_effort_escalation = False
    request = InternalRequest(
        messages=[Message(role="user", content="short ask")],
        model="daari",
        sampling=SamplingParams(reasoning_effort="high"),
        meta=RequestMeta(no_cache=True),
    )
    assert router._choose_uncapped_tier(request) == "L3"


@pytest.mark.asyncio
async def test_reasoning_effort_reaches_ollama_wire(settings, tmp_path, monkeypatch):
    settings.cache.l0.enabled = False
    settings.cache.l1.enabled = False
    settings.models.l3 = "gpt-oss:20b"
    settings.routing.max_tier_for_chat = "L3"
    bodies: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        bodies.append(json.loads(request.content))
        return httpx.Response(200, json={"message": {"content": "ok"}})

    transport = httpx.MockTransport(handler)
    real = httpx.AsyncClient

    def factory(*args, **kwargs):
        kwargs["transport"] = transport
        return real(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", factory)
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/chat/completions",
            json={
                "model": "daari",
                "messages": [{"role": "user", "content": "hello there"}],
                "reasoning_effort": "medium",
            },
            headers=META_HEADERS,
        )
    assert response.status_code == 200
    assert bodies[0]["think"] == "medium"
    assert response.json()["daari_meta"]["reasoning_effort"] == "medium"
