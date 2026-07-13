"""Train 2 deeper token savings: prompt-cache passthrough, compaction, compression (issue #71)."""

from __future__ import annotations

import json

import httpx
import pytest

from daari.cache.exact import ExactCache
from daari.cache.semantic import SemanticCache
from daari.config.settings import Settings
from daari.gateway.internal import DaariMeta, InternalRequest, InternalResponse, Message
from daari.observability.metrics import Metrics
from daari.router.compress import compress_messages
from daari.router.frontier import FrontierExecutor
from daari.router.router import OllamaExecutor, Router


def _response(content: str, tier: str = "L3") -> InternalResponse:
    return InternalResponse(
        content=content,
        model="llama3.2:3b",
        daari_meta=DaariMeta(tier=tier, executor="ollama", provider_id="ollama", latency_ms=1),
    )


class NullEmbedder:
    async def embed(self, text: str):
        return None


def _router(tmp_path, **kwargs) -> Router:
    executor = OllamaExecutor(base_url="http://test", default_model="llama3.2:3b", tier="L3")
    return Router(
        cache=ExactCache(str(tmp_path / "l0"), enabled=False),
        semantic_cache=SemanticCache(str(tmp_path / "l1"), NullEmbedder(), enabled=False),
        ollama=executor,
        metrics=Metrics(),
        frontier=None,
        frontier_enabled=False,
        **kwargs,
    )


class TestPromptCachePassthrough:
    @pytest.mark.asyncio
    async def test_anthropic_system_prefix_gets_cache_control(self):
        captured: dict = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured.update(json.loads(request.content))
            return httpx.Response(
                200, json={"choices": [{"message": {"content": "hi"}}]}
            )

        executor = FrontierExecutor(
            base_url="https://api.anthropic.com/v1",
            default_model="claude-3-5-haiku-latest",
            api_key="k",
            provider="anthropic",
            transport=httpx.MockTransport(handler),
        )
        await executor.execute(
            InternalRequest(
                messages=[
                    Message(role="system", content="You are a stable long system prompt."),
                    Message(role="user", content="hello"),
                ],
                model="daari",
            ),
            escalated_from="L3",
            local_confidence=0.4,
        )

        system = captured["messages"][0]
        assert isinstance(system["content"], list)
        assert system["content"][0]["cache_control"] == {"type": "ephemeral"}
        assert system["content"][0]["text"] == "You are a stable long system prompt."
        # Non-system messages stay plain strings.
        assert captured["messages"][1]["content"] == "hello"

    @pytest.mark.asyncio
    async def test_openai_payload_untouched(self):
        captured: dict = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured.update(json.loads(request.content))
            return httpx.Response(
                200, json={"choices": [{"message": {"content": "hi"}}]}
            )

        executor = FrontierExecutor(
            base_url="https://api.openai.com/v1",
            default_model="gpt-4o-mini",
            api_key="k",
            provider="openai",
            transport=httpx.MockTransport(handler),
        )
        await executor.execute(
            InternalRequest(
                messages=[
                    Message(role="system", content="Stable prompt."),
                    Message(role="user", content="hello"),
                ],
                model="daari",
            ),
            escalated_from="L3",
            local_confidence=0.4,
        )
        assert captured["messages"][0]["content"] == "Stable prompt."

    @pytest.mark.asyncio
    async def test_prompt_cache_disabled_keeps_plain_strings(self):
        captured: dict = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured.update(json.loads(request.content))
            return httpx.Response(
                200, json={"choices": [{"message": {"content": "hi"}}]}
            )

        executor = FrontierExecutor(
            base_url="https://api.anthropic.com/v1",
            default_model="claude-3-5-haiku-latest",
            api_key="k",
            provider="anthropic",
            prompt_cache=False,
            transport=httpx.MockTransport(handler),
        )
        await executor.execute(
            InternalRequest(
                messages=[
                    Message(role="system", content="Stable prompt."),
                    Message(role="user", content="hello"),
                ],
                model="daari",
            ),
            escalated_from="L3",
            local_confidence=0.4,
        )
        assert captured["messages"][0]["content"] == "Stable prompt."

    def test_slimming_keeps_system_prefix_byte_stable(self, tmp_path):
        """T2a invariant: the slimmer must never rewrite or reorder system text."""
        router = _router(tmp_path, frontier_slim_prompts=True)
        system_a = "First system prompt.\n\nWith details."
        system_b = "Second system prompt."
        request = InternalRequest(
            messages=[
                Message(role="system", content=system_a),
                Message(role="system", content=system_b),
                *[
                    Message(role="user", content=f"turn {i}   \n\n\n\n\nnoise")
                    for i in range(12)
                ],
            ],
            model="daari",
        )
        first = router._slim_for_frontier(request)
        second = router._slim_for_frontier(request)

        for slimmed in (first, second):
            systems = [m.content for m in slimmed.messages if m.role == "system"]
            assert systems == [system_a, system_b], "prefix must stay byte-stable"


class CountingL3:
    def __init__(self):
        self.calls = 0
        self.default_model = "llama3.2:3b"
        self.base_url = "http://test"
        self.tier = "L3"

    async def execute(self, request: InternalRequest) -> InternalResponse:
        self.calls += 1
        return _response("Summary: user discussed apples then oranges.")


class TestConversationCompaction:
    def _request(self, turns: int) -> InternalRequest:
        return InternalRequest(
            messages=[
                Message(role="system", content="sys"),
                *[
                    Message(
                        role="user" if i % 2 == 0 else "assistant",
                        content=f"turn number {i} about topic {i}",
                    )
                    for i in range(turns)
                ],
            ],
            model="daari",
        )

    @pytest.mark.asyncio
    async def test_old_turns_become_pinned_summary(self, tmp_path):
        router = _router(tmp_path, context_compact=True, context_max_history=4)
        router.ollama_l3 = CountingL3()

        compacted = await router._compact_context(self._request(10))

        contents = [m.content for m in compacted.messages]
        assert any("Earlier conversation summary" in c for c in contents)
        assert any("apples then oranges" in c for c in contents)
        # The last 4 non-system turns survive verbatim.
        assert "turn number 9 about topic 9" in contents[-1]
        assert not any("turn number 0 " in c for c in contents)

    @pytest.mark.asyncio
    async def test_summary_cached_per_prefix(self, tmp_path):
        router = _router(tmp_path, context_compact=True, context_max_history=4)
        counting = CountingL3()
        router.ollama_l3 = counting

        await router._compact_context(self._request(10))
        await router._compact_context(self._request(10))

        assert counting.calls == 1, "same prefix must not be re-summarized"

    @pytest.mark.asyncio
    async def test_short_history_untouched(self, tmp_path):
        router = _router(tmp_path, context_compact=True, context_max_history=4)
        counting = CountingL3()
        router.ollama_l3 = counting

        request = self._request(3)
        compacted = await router._compact_context(request)

        assert compacted is request
        assert counting.calls == 0

    @pytest.mark.asyncio
    async def test_tool_flows_never_compacted(self, tmp_path):
        router = _router(tmp_path, context_compact=True, context_max_history=4)
        request = self._request(10)
        request.tools = [{"type": "function", "function": {"name": "x"}}]
        compacted = await router._compact_context(request)
        assert compacted is request

    @pytest.mark.asyncio
    async def test_summarizer_failure_falls_back_to_original(self, tmp_path):
        router = _router(tmp_path, context_compact=True, context_max_history=4)

        class Broken:
            default_model = "llama3.2:3b"

            async def execute(self, request):
                raise RuntimeError("down")

        router.ollama_l3 = Broken()
        request = self._request(10)
        compacted = await router._compact_context(request)
        assert compacted is request

    def test_settings_default_off(self):
        settings = Settings.model_validate({})
        assert settings.context_optimizer.compact is False
        assert settings.frontier.compress_context is False
        assert settings.frontier.prompt_cache is True


class RelevanceEmbedder:
    """'database' sentences align with the query; others are orthogonal."""

    async def embed(self, text: str):
        if "database" in text.lower():
            return [1.0, 0.0]
        return [0.0, 1.0]


class TestFrontierCompression:
    @pytest.mark.asyncio
    async def test_prunes_irrelevant_sentences(self):
        filler = " ".join(f"Filler sentence number {i} about the weather." for i in range(30))
        messages = [
            Message(role="system", content="sys"),
            Message(
                role="user",
                content=f"The database uses postgres. {filler} The database schema has ten tables.",
            ),
            Message(role="user", content="How do I optimize the database?"),
        ]
        compressed, before, after = await compress_messages(
            messages, embedder=RelevanceEmbedder(), target_ratio=0.3
        )
        assert after < before
        body = compressed[1].content
        assert "database uses postgres" in body
        assert "schema has ten tables" in body
        assert "Filler sentence number 29" not in body
        # Query message and system message are untouched.
        assert compressed[0].content == "sys"
        assert compressed[2].content == "How do I optimize the database?"

    @pytest.mark.asyncio
    async def test_short_messages_untouched(self):
        messages = [
            Message(role="user", content="short context"),
            Message(role="user", content="the question"),
        ]
        compressed, before, after = await compress_messages(
            messages, embedder=RelevanceEmbedder(), target_ratio=0.3
        )
        assert [m.content for m in compressed] == ["short context", "the question"]
        assert before == after

    @pytest.mark.asyncio
    async def test_embedding_failure_returns_original(self):
        long_text = " ".join(f"Sentence {i}." for i in range(200))
        messages = [
            Message(role="user", content=long_text),
            Message(role="user", content="question"),
        ]
        compressed, before, after = await compress_messages(
            messages, embedder=NullEmbedder(), target_ratio=0.3
        )
        assert compressed[0].content == long_text
        assert before == after
