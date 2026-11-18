"""Client bodies cannot smuggle credential fields into upstream payloads (#2252).

Fences the LiteLLM #51254 class: tenant_id / client_secret / os.environ/ /
secret:// values in a chat or Messages body must never reach the forwarded
OpenAI/Anthropic payload or trigger secret resolution.
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from daari.gateway.anthropic import AnthropicRequest
from daari.gateway.internal import DaariMeta, InternalResponse
from daari.gateway.openai import ChatCompletionRequest
from daari.gateway.sampling import SamplingParams
from daari.router.anthropic_messages import to_anthropic_payload
from daari.router.frontier import FrontierExecutor
from daari.router.router import AppContext
from daari.server.app import create_app
from tests.conftest import META_HEADERS

_SMUGGLE = {
    "tenant_id": "evil-tenant",
    "client_id": "evil-client",
    "client_secret": "os.environ/OPENAI_API_KEY",
    "api_key": "secret://exec/echo#pwned",
    "base_url": "https://evil.example/v1",
}

_FORBIDDEN = frozenset(_SMUGGLE) | {
    "os.environ/OPENAI_API_KEY",
    "secret://exec/echo#pwned",
}


def _assert_clean_payload(payload: dict) -> None:
    blob = repr(payload)
    for key in _SMUGGLE:
        assert key not in payload, key
    for needle in _FORBIDDEN:
        assert needle not in blob, needle


def _frontier_executor(router) -> FrontierExecutor:
    frontier = router.frontier
    if isinstance(frontier, FrontierExecutor):
        return frontier
    slots = getattr(frontier, "slots", None) or []
    assert slots, "expected FrontierPool slots"
    return slots[0].executor


def test_openai_payload_allowlist_excludes_credential_fields():
    params = SamplingParams(max_tokens=16, top_p=0.9)
    object.__setattr__(params, "tenant_id", "evil")
    object.__setattr__(params, "client_secret", "secret://exec/x")
    object.__setattr__(params, "api_key", "sk-evil")
    payload = params.openai_payload()
    _assert_clean_payload(payload)
    assert "max_tokens" in payload
    assert "tenant_id" not in payload


def test_chat_and_messages_models_drop_credential_extras():
    chat = ChatCompletionRequest.model_validate(
        {
            "model": "daari",
            "messages": [{"role": "user", "content": "hi"}],
            **_SMUGGLE,
        }
    )
    dumped = chat.model_dump()
    for key in _SMUGGLE:
        assert key not in dumped
    messages = AnthropicRequest.model_validate(
        {
            "model": "claude-sonnet-5",
            "messages": [{"role": "user", "content": "hi"}],
            "max_tokens": 32,
            **_SMUGGLE,
        }
    )
    dumped = messages.model_dump()
    for key in _SMUGGLE:
        assert key not in dumped


@pytest.mark.asyncio
async def test_chat_completions_smuggle_fields_never_reach_upstream(
    settings, monkeypatch
):
    settings.cache.l0.enabled = False
    settings.cache.l1.enabled = False
    settings.frontier.enabled = True
    settings.frontier.base_url = "http://frontier.test/v1"
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

    resolve_calls: list[str] = []

    def _forbid_resolve(ref: str, *args, **kwargs):
        resolve_calls.append(ref)
        raise AssertionError(f"secret resolution must not run for client body: {ref}")

    monkeypatch.setattr(
        "daari.security.secret_refs.resolve_secret_ref", _forbid_resolve
    )

    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    captured: dict = {}

    async def fake_local(request):
        raise AssertionError("local must not answer web_search_options")

    async def fake_l6(request, *, escalated_from: str, local_confidence: float):
        executor = _frontier_executor(app.state.ctx.router)
        captured["payload"] = executor._openai_payload(request, stream=False)
        return InternalResponse(
            content="ok",
            model="gpt-4o-mini",
            daari_meta=DaariMeta(
                tier="L6",
                executor="frontier",
                provider_id="openai",
                latency_ms=5,
                escalated_from=escalated_from,
                confidence=local_confidence,
                warning="web_search_required",
            ),
        )

    monkeypatch.setattr(app.state.ctx.router.ollama_l3, "execute", fake_local)
    monkeypatch.setattr(app.state.ctx.router.ollama_l4, "execute", fake_local)
    monkeypatch.setattr(app.state.ctx.router.ollama_l5, "execute", fake_local)
    # Frontier may be a single executor or a pool of slots.
    frontier = app.state.ctx.router.frontier
    if isinstance(frontier, FrontierExecutor):
        monkeypatch.setattr(frontier, "execute", fake_l6)
    else:
        for slot in frontier.slots:
            monkeypatch.setattr(slot.executor, "execute", fake_l6)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/chat/completions",
            json={
                "model": "daari",
                "messages": [{"role": "user", "content": "latest headlines?"}],
                "web_search_options": {"search_context_size": "low"},
                **_SMUGGLE,
            },
            headers=META_HEADERS,
        )
    assert response.status_code == 200, response.text
    assert "payload" in captured
    _assert_clean_payload(captured["payload"])
    assert resolve_calls == []


@pytest.mark.asyncio
async def test_messages_smuggle_fields_never_reach_upstream(settings, monkeypatch):
    settings.cache.l0.enabled = False
    settings.cache.l1.enabled = False
    settings.frontier.enabled = True
    settings.frontier.base_url = "https://api.anthropic.com"
    settings.frontier.model = "claude-sonnet-5"
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

    resolve_calls: list[str] = []

    def _forbid_resolve(ref: str, *args, **kwargs):
        resolve_calls.append(ref)
        raise AssertionError(f"secret resolution must not run for client body: {ref}")

    monkeypatch.setattr(
        "daari.security.secret_refs.resolve_secret_ref", _forbid_resolve
    )

    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    captured: dict = {}

    async def fake_local(request):
        # Stub upstream: build the Anthropic Messages body that would be
        # forwarded for this InternalRequest and prove smuggle fields are gone.
        captured["payload"] = to_anthropic_payload(
            request,
            model="claude-sonnet-5",
            stream=False,
        )
        return InternalResponse(
            content="ok",
            model=settings.models.l3,
            daari_meta=DaariMeta(
                tier="L3",
                executor="ollama",
                provider_id="ollama",
                latency_ms=5,
            ),
        )

    monkeypatch.setattr(app.state.ctx.router.ollama_l3, "execute", fake_local)
    monkeypatch.setattr(app.state.ctx.router.ollama_l4, "execute", fake_local)
    monkeypatch.setattr(app.state.ctx.router.ollama_l5, "execute", fake_local)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/messages",
            json={
                "model": "claude-sonnet-5",
                "max_tokens": 64,
                "messages": [{"role": "user", "content": "hi"}],
                **_SMUGGLE,
            },
            headers={
                **META_HEADERS,
                "anthropic-version": "2023-06-01",
                "x-api-key": "sk-ant-test",
            },
        )
    assert response.status_code == 200, response.text
    assert "payload" in captured
    _assert_clean_payload(captured["payload"])
    assert resolve_calls == []
