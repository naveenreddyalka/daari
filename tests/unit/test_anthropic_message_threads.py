"""Anthropic message-threads create/continue passthrough (#2093)."""

from __future__ import annotations

import json

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError

from daari.cache.exact import cache_key
from daari.cache.semantic import semantic_context_key
from daari.gateway.anthropic import AnthropicRequest
from daari.gateway.internal import InternalRequest, Message, RequestMeta
from daari.router.anthropic_messages import (
    THREAD_BETA,
    clear_anthropic_thread_creates,
    normalize_anthropic_thread,
    thread_cache_token,
    to_anthropic_payload,
)
from daari.router.frontier import FrontierExecutor
from daari.router.router import AppContext
from daari.server.app import create_app
from tests.conftest import META_HEADERS


@pytest.fixture(autouse=True)
def _reset_thread_registry() -> None:
    clear_anthropic_thread_creates()
    yield
    clear_anthropic_thread_creates()


def test_anthropic_request_accepts_create_and_continue_thread() -> None:
    create = AnthropicRequest(
        model="claude-sonnet-5-5",
        messages=[{"role": "user", "content": "hi"}],
        thread={"type": "create"},
    )
    assert create.thread == {"type": "create"}
    cont = AnthropicRequest(
        model="claude-sonnet-5-5",
        messages=[{"role": "user", "content": "again"}],
        thread={"type": "continue", "previous_message_id": "msg_abc"},
    )
    assert cont.thread["type"] == "continue"
    assert cont.thread["previous_message_id"] == "msg_abc"


def test_anthropic_request_absent_thread_unchanged() -> None:
    body = AnthropicRequest(
        model="claude-sonnet-5-5",
        messages=[{"role": "user", "content": "hi"}],
    )
    assert body.thread is None


def test_unknown_thread_type_fails_closed() -> None:
    with pytest.raises((ValidationError, ValueError)):
        normalize_anthropic_thread({"type": "resume"})
    with pytest.raises(ValidationError):
        AnthropicRequest(
            model="claude-sonnet-5-5",
            messages=[{"role": "user", "content": "hi"}],
            thread={"type": "resume"},
        )


def test_continue_requires_previous_message_id() -> None:
    with pytest.raises((ValidationError, ValueError)):
        normalize_anthropic_thread({"type": "continue"})


def test_to_anthropic_payload_forwards_thread() -> None:
    thread = {"type": "continue", "previous_message_id": "msg_xyz"}
    payload = to_anthropic_payload(
        InternalRequest(
            messages=[Message(role="user", content="hi")],
            model="daari",
            meta=RequestMeta(anthropic_thread=thread),
        ),
        model="claude-sonnet-5-5",
    )
    assert payload["thread"] == thread


def test_to_anthropic_payload_omits_thread_when_absent() -> None:
    payload = to_anthropic_payload(
        InternalRequest(
            messages=[Message(role="user", content="hi")],
            model="daari",
        ),
        model="claude-sonnet-5-5",
    )
    assert "thread" not in payload


def test_cache_keys_differ_across_create_continue_and_absent() -> None:
    base = dict(messages=[Message(role="user", content="same")], model="daari")
    absent = cache_key(InternalRequest(**base))
    create = cache_key(
        InternalRequest(**base, meta=RequestMeta(anthropic_thread={"type": "create"}))
    )
    cont = cache_key(
        InternalRequest(
            **base,
            meta=RequestMeta(
                anthropic_thread={"type": "continue", "previous_message_id": "msg_1"}
            ),
        )
    )
    cont2 = cache_key(
        InternalRequest(
            **base,
            meta=RequestMeta(
                anthropic_thread={"type": "continue", "previous_message_id": "msg_2"}
            ),
        )
    )
    assert len({absent, create, cont, cont2}) == 4
    assert thread_cache_token({"type": "create"}) != thread_cache_token(
        {"type": "continue", "previous_message_id": "msg_1"}
    )
    assert semantic_context_key(
        InternalRequest(**base, meta=RequestMeta(anthropic_thread={"type": "create"}))
    ) != semantic_context_key(InternalRequest(**base))


def test_thread_beta_constant() -> None:
    assert THREAD_BETA == "message-threads-2026-08-12"


@pytest.mark.asyncio
async def test_create_body_survives_to_mocked_l6_payload(settings, monkeypatch):
    from daari.gateway.internal import DaariMeta, InternalResponse

    settings.frontier.enabled = True
    settings.frontier.provider = "anthropic"
    settings.frontier.base_url = "https://api.anthropic.com"
    settings.frontier.model = "claude-sonnet-5-5"
    application = create_app(settings)
    application.state.ctx = AppContext.from_settings(settings)

    captured: list[dict] = []
    seen_beta: list[str | None] = []

    async def fake_route(request: InternalRequest) -> InternalResponse:
        stub = FrontierExecutor(
            base_url="https://api.anthropic.com",
            default_model="claude-sonnet-5-5",
            api_key="sk-ant-test",
            provider="anthropic",
        )
        captured.append(stub._anthropic_payload(request, stream=False))
        seen_beta.append(request.meta.anthropic_beta)
        return InternalResponse(
            content="ok",
            model="claude-sonnet-5-5",
            daari_meta=DaariMeta(tier="L6", executor="frontier", latency_ms=1),
        )

    application.state.ctx.router.route = fake_route  # type: ignore[method-assign]

    events: list[tuple[str, dict]] = []

    def capture_event(name: str, payload: dict | None = None, **kwargs) -> None:
        events.append((name, dict(payload or kwargs)))

    monkeypatch.setattr("daari.gateway.anthropic.log_gateway_event", capture_event)

    transport = ASGITransport(app=application)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/v1/messages",
            headers={
                **META_HEADERS,
                "anthropic-version": "2023-06-01",
                "anthropic-beta": THREAD_BETA,
                "x-api-key": "test",
                "X-Daari-Tier-Override": "L6",
            },
            json={
                "model": "claude-sonnet-5-5",
                "max_tokens": 16,
                "messages": [{"role": "user", "content": "hi"}],
                "thread": {"type": "create"},
            },
        )
    assert response.status_code == 200, response.text
    assert captured
    assert captured[0]["thread"] == {"type": "create"}
    assert seen_beta == [THREAD_BETA]
    thread_events = [e for e in events if e[0] == "anthropic_message_thread"]
    assert thread_events
    assert thread_events[0][1].get("type") == "create"
    assert "content" not in thread_events[0][1]
    assert "messages" not in thread_events[0][1]


def _patch_local_executors(application, fake_local) -> None:
    for tier in ("ollama_l3", "ollama_l4", "ollama_l5"):
        setattr(getattr(application.state.ctx.router, tier), "execute", fake_local)


@pytest.mark.asyncio
async def test_continue_without_create_on_local_fails_closed(settings):
    from daari.gateway.internal import DaariMeta, InternalResponse

    settings.frontier.enabled = False
    application = create_app(settings)
    application.state.ctx = AppContext.from_settings(settings)

    async def fake_local(request):
        return InternalResponse(
            content="should-not-run",
            model="llama3.2:3b",
            daari_meta=DaariMeta(tier="L3", executor="ollama", latency_ms=1),
        )

    _patch_local_executors(application, fake_local)

    transport = ASGITransport(app=application)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/v1/messages",
            headers={
                **META_HEADERS,
                "anthropic-version": "2023-06-01",
                "x-api-key": "test",
                "X-Daari-No-Frontier": "true",
            },
            json={
                "model": "daari",
                "max_tokens": 16,
                "messages": [{"role": "user", "content": "hi"}],
                "thread": {
                    "type": "continue",
                    "previous_message_id": "msg_orphan",
                },
            },
        )
    assert response.status_code == 400
    detail = response.json().get("detail") or response.json()
    assert "thread" in json.dumps(detail).lower()


@pytest.mark.asyncio
async def test_create_on_local_ignored_with_warning(settings):
    from daari.gateway.internal import DaariMeta, InternalResponse

    settings.frontier.enabled = False
    application = create_app(settings)
    application.state.ctx = AppContext.from_settings(settings)

    async def fake_local(request):
        return InternalResponse(
            content="local-ok",
            model="llama3.2:3b",
            daari_meta=DaariMeta(tier="L3", executor="ollama", latency_ms=1),
        )

    _patch_local_executors(application, fake_local)

    transport = ASGITransport(app=application)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/v1/messages",
            headers={
                **META_HEADERS,
                "anthropic-version": "2023-06-01",
                "x-api-key": "test",
                "X-Daari-No-Frontier": "true",
            },
            json={
                "model": "daari",
                "max_tokens": 16,
                "messages": [{"role": "user", "content": "hi"}],
                "thread": {"type": "create"},
            },
        )
    assert response.status_code == 200, response.text
    body = response.json()
    warning = (body.get("daari_meta") or {}).get("warning") or ""
    assert "thread" in warning.lower() or "message_thread" in warning.lower()


@pytest.mark.asyncio
async def test_continue_soft_ignore_on_local(settings):
    from daari.gateway.internal import DaariMeta, InternalResponse

    settings.frontier.enabled = False
    settings.anthropic.thread_continue_soft = True
    application = create_app(settings)
    application.state.ctx = AppContext.from_settings(settings)

    async def fake_local(request):
        assert request.meta.anthropic_thread is None
        return InternalResponse(
            content="local-ok",
            model="llama3.2:3b",
            daari_meta=DaariMeta(tier="L3", executor="ollama", latency_ms=1),
        )

    _patch_local_executors(application, fake_local)

    transport = ASGITransport(app=application)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/v1/messages",
            headers={
                **META_HEADERS,
                "anthropic-version": "2023-06-01",
                "x-api-key": "test",
                "X-Daari-No-Frontier": "true",
            },
            json={
                "model": "daari",
                "max_tokens": 16,
                "messages": [{"role": "user", "content": "hi"}],
                "thread": {
                    "type": "continue",
                    "previous_message_id": "msg_orphan",
                },
            },
        )
    assert response.status_code == 200, response.text
    warning = (response.json().get("daari_meta") or {}).get("warning") or ""
    assert "thread" in warning.lower() or "message_thread" in warning.lower()


def test_claude_code_docs_mention_message_threads() -> None:
    from pathlib import Path

    text = Path("docs/developer/guides/clients/claude-code.md").read_text()
    assert "message-threads" in text.lower() or "message threads" in text.lower()
    assert "L6" in text
