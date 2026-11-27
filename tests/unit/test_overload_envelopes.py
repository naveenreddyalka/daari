"""Typed overload envelopes when routing exhausts on 429/529 (#2348)."""

from __future__ import annotations

import json

import httpx
import pytest
from httpx import ASGITransport, AsyncClient

from daari.gateway.client_errors import (
    is_upstream_overload,
    overload_json_response,
    overload_stream_frame,
    routing_failure_detail,
)
from daari.gateway.internal import InternalRequest
from daari.security.secret_refs import clear_registered_secrets, register_secret
from daari.server.app import AppContext, create_app


def _status(code: int, retry_after: str | None = None) -> httpx.HTTPStatusError:
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    headers = {"Retry-After": retry_after} if retry_after else None
    response = httpx.Response(code, request=request, headers=headers)
    return httpx.HTTPStatusError("boom", request=request, response=response)


def test_overload_classification_walks_the_cause_chain():
    wrapped = RuntimeError("routing exhausted")
    wrapped.__cause__ = _status(529, retry_after="3")
    assert is_upstream_overload(wrapped) is True
    assert is_upstream_overload(_status(500)) is False
    assert is_upstream_overload(RuntimeError("config")) is False
    openai = overload_json_response(wrapped)
    assert openai is not None
    assert openai.status_code == 503
    assert openai.headers["retry-after"] == "3"
    body = json.loads(openai.body)
    assert body["error"]["type"] == "server_is_overloaded"
    assert body["error"]["message"].startswith("Routing failed:")
    anthropic = overload_json_response(wrapped, anthropic=True)
    assert anthropic is not None
    assert anthropic.status_code == 529
    anthropic_body = json.loads(anthropic.body)
    assert anthropic_body["type"] == "error"
    assert anthropic_body["error"]["type"] == "overloaded_error"
    assert overload_json_response(RuntimeError("nope")) is None


def test_overload_message_redacts_secrets():
    clear_registered_secrets()
    register_secret("sk-overload-secret")
    try:
        request = httpx.Request("POST", "https://api.openai.com/v1/chat/completions")
        response = httpx.Response(429, request=request, text="key sk-overload-secret")
        exc = httpx.HTTPStatusError(
            "key sk-overload-secret", request=request, response=response
        )
        body = json.loads(overload_json_response(exc).body)
        assert "sk-overload-secret" not in body["error"]["message"]
        assert body["error"]["message"].startswith("Routing failed:")
        frame = overload_stream_frame(exc)
        assert frame is not None
        assert "server_is_overloaded" in frame
        assert "sk-overload-secret" not in frame
    finally:
        clear_registered_secrets()


def test_non_overload_detail_stays_a_routing_failed_string():
    detail = routing_failure_detail(_status(502))
    assert detail.startswith("Routing failed:")
    assert "server_is_overloaded" not in detail


@pytest.fixture
def app(settings):
    application = create_app(settings)
    application.state.ctx = AppContext.from_settings(settings)
    return application


@pytest.mark.asyncio
async def test_chat_overload_is_503_server_is_overloaded(app):
    async def explode(request: InternalRequest):
        raise _status(429, retry_after="2")

    app.state.ctx.router.route = explode
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/chat/completions",
            json={"model": "daari", "messages": [{"role": "user", "content": "hi"}]},
        )
    assert response.status_code == 503
    assert response.json()["error"]["type"] == "server_is_overloaded"
    assert response.headers["retry-after"] == "2"


@pytest.mark.asyncio
async def test_chat_non_overload_keeps_routing_failed_detail(app):
    async def explode(request: InternalRequest):
        raise _status(500)

    app.state.ctx.router.route = explode
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/chat/completions",
            json={"model": "daari", "messages": [{"role": "user", "content": "hi"}]},
        )
    assert response.status_code == 503
    assert "Routing failed:" in response.json()["detail"]
    assert "server_is_overloaded" not in response.text


@pytest.mark.asyncio
async def test_messages_overload_is_529_overloaded_error(app):
    async def explode(request: InternalRequest):
        raise _status(529)

    app.state.ctx.router.route = explode
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/messages",
            json={
                "model": "daari",
                "max_tokens": 8,
                "messages": [{"role": "user", "content": "hi"}],
            },
        )
    assert response.status_code == 529
    body = response.json()
    assert body["type"] == "error"
    assert body["error"]["type"] == "overloaded_error"
    assert response.headers["retry-after"] == "1"


@pytest.mark.asyncio
async def test_chat_stream_emits_overload_frame_before_done(app):
    async def explode(request: InternalRequest, outcome=None):
        if False:
            yield ""
        raise _status(529)

    app.state.ctx.router.stream_openai_chunks = explode
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/chat/completions",
            json={
                "model": "daari",
                "stream": True,
                "messages": [{"role": "user", "content": "hi"}],
            },
        )
    assert response.status_code == 200
    assert "server_is_overloaded" in response.text
    assert response.text.strip().endswith("[DONE]")


@pytest.mark.asyncio
async def test_messages_stream_emits_overloaded_error_frame(app):
    async def explode(request: InternalRequest, outcome=None):
        if False:
            yield ""
        raise _status(429)

    app.state.ctx.router.stream_anthropic_events = explode
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/messages",
            json={
                "model": "daari",
                "max_tokens": 8,
                "stream": True,
                "messages": [{"role": "user", "content": "hi"}],
            },
        )
    assert "overloaded_error" in response.text
