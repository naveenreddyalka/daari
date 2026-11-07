"""Codex PAT (`at-…`) routes L6 to chatgpt.com/backend-api/codex (#2112)."""

from __future__ import annotations

import httpx
import pytest

from daari.gateway.internal import InternalRequest, Message
from daari.router.frontier import (
    DEFAULT_CODEX_BASE_URL,
    FrontierExecutor,
    is_codex_pat,
    resolve_frontier_base_url,
)
from daari.router.retry import RetryPolicy
from daari.security.offline_mode import (
    OfflineEgressBlocked,
    configure_offline_mode,
)


def _request() -> InternalRequest:
    return InternalRequest(model="gpt-4o-mini", messages=[Message(role="user", content="hi")])


def test_resolve_frontier_base_url_for_codex_pat():
    openai = "https://api.openai.com/v1"
    assert resolve_frontier_base_url("sk-abc", base_url=openai) == openai
    assert resolve_frontier_base_url(None, base_url=openai) == openai
    assert (
        resolve_frontier_base_url("at-codex-pat", base_url=openai)
        == DEFAULT_CODEX_BASE_URL
    )
    assert (
        resolve_frontier_base_url(
            "at-codex-pat",
            base_url=openai,
            codex_base_url="https://example.test/codex",
        )
        == "https://example.test/codex"
    )
    # Empty override opts out of rewrite.
    assert (
        resolve_frontier_base_url(
            "at-codex-pat",
            base_url=openai,
            codex_base_url="",
        )
        == openai
    )
    assert is_codex_pat("at-xyz") is True
    assert is_codex_pat("sk-xyz") is False


@pytest.mark.asyncio
async def test_frontier_executor_at_key_hits_codex_host():
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return httpx.Response(
            200,
            json={
                "id": "chatcmpl-1",
                "choices": [
                    {"message": {"role": "assistant", "content": "ok"}, "finish_reason": "stop"}
                ],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            },
        )

    executor = FrontierExecutor(
        base_url="https://api.openai.com/v1",
        default_model="gpt-4o-mini",
        api_key="at-test-pat",
        provider="openai",
        transport=httpx.MockTransport(handler),
        retry=RetryPolicy(attempts=1, base_delay=0.0, max_delay=0.0, jitter=0.0),
    )
    await executor.execute(_request(), escalated_from="L3", local_confidence=0.1)
    assert seen
    assert seen[0].startswith(f"{DEFAULT_CODEX_BASE_URL}/chat/completions")


@pytest.mark.asyncio
async def test_frontier_executor_sk_key_keeps_openai_host():
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return httpx.Response(
            200,
            json={
                "id": "chatcmpl-1",
                "choices": [
                    {"message": {"role": "assistant", "content": "ok"}, "finish_reason": "stop"}
                ],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            },
        )

    executor = FrontierExecutor(
        base_url="https://api.openai.com/v1",
        default_model="gpt-4o-mini",
        api_key="sk-test",
        provider="openai",
        transport=httpx.MockTransport(handler),
        retry=RetryPolicy(attempts=1, base_delay=0.0, max_delay=0.0, jitter=0.0),
    )
    await executor.execute(_request(), escalated_from="L3", local_confidence=0.1)
    assert seen
    assert seen[0].startswith("https://api.openai.com/v1/chat/completions")


@pytest.mark.asyncio
async def test_codex_pat_still_blocked_in_offline_mode():
    configure_offline_mode(enabled=True, allow_hosts=[])
    try:

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={})

        executor = FrontierExecutor(
            base_url="https://api.openai.com/v1",
            default_model="gpt-4o-mini",
            api_key="at-test-pat",
            provider="openai",
            transport=httpx.MockTransport(handler),
            retry=RetryPolicy(attempts=1, base_delay=0.0, max_delay=0.0, jitter=0.0),
        )
        with pytest.raises(OfflineEgressBlocked):
            await executor.execute(_request(), escalated_from="L3", local_confidence=0.1)
    finally:
        configure_offline_mode(enabled=False, allow_hosts=[])


def test_frontier_settings_default_codex_base_url():
    from daari.config.settings import FrontierSettings

    frontier = FrontierSettings()
    assert frontier.codex_base_url == DEFAULT_CODEX_BASE_URL


def test_build_frontier_pool_passes_codex_base_url(monkeypatch):
    from daari.config.settings import Settings
    from daari.router.frontier_pool import build_frontier_pool

    settings = Settings()
    settings.frontier.enabled = True
    settings.frontier.base_url = "https://api.openai.com/v1"
    settings.frontier.codex_base_url = "https://chatgpt.com/backend-api/codex"
    monkeypatch.setenv("DAARI_FRONTIER_API_KEY", "at-from-env")
    pool = build_frontier_pool(settings)
    assert pool.slots[0].executor.codex_base_url == "https://chatgpt.com/backend-api/codex"
    assert pool.slots[0].executor.effective_base_url() == DEFAULT_CODEX_BASE_URL
