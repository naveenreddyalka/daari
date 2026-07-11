"""Context optimizer: history trimming + whitespace squeeze (issue #22)."""

from __future__ import annotations

import pytest

from daari.cache.exact import ExactCache
from daari.cache.semantic import SemanticCache
from daari.gateway.internal import DaariMeta, InternalRequest, InternalResponse, Message
from daari.observability.metrics import Metrics
from daari.observability.trace import TraceStore
from daari.router.context_optimizer import optimize_messages
from daari.router.router import OllamaExecutor, Router
from tests.conftest import NoopEmbedder


def _msgs(count: int) -> list[Message]:
    return [Message(role="user", content=f"turn {i}") for i in range(count)]


class TestOptimizeMessages:
    def test_trims_to_system_plus_last_n(self):
        messages = [Message(role="system", content="sys"), *_msgs(30)]
        optimized, before, after = optimize_messages(messages, max_history_messages=10)
        assert len(optimized) == 11
        assert optimized[0].role == "system"
        assert optimized[1].content == "turn 20"
        assert optimized[-1].content == "turn 29"
        assert after < before

    def test_short_history_untouched(self):
        messages = [Message(role="system", content="sys"), *_msgs(3)]
        optimized, before, after = optimize_messages(messages, max_history_messages=10)
        assert [m.content for m in optimized] == [m.content for m in messages]
        assert before == after

    def test_keeps_all_system_messages(self):
        messages = [
            Message(role="system", content="sys1"),
            *_msgs(15),
            Message(role="system", content="sys2"),
        ]
        optimized, _, _ = optimize_messages(messages, max_history_messages=5)
        assert [m.content for m in optimized if m.role == "system"] == ["sys1", "sys2"]

    def test_squeezes_whitespace(self):
        messages = [Message(role="user", content="line one   \n\n\n\n\n\nline two  ")]
        optimized, before, after = optimize_messages(messages, max_history_messages=10)
        assert optimized[0].content == "line one\n\n\nline two"
        assert after < before

    def test_squeeze_can_be_disabled(self):
        content = "a   \n\n\n\n\nb"
        messages = [Message(role="user", content=content)]
        optimized, _, _ = optimize_messages(
            messages, max_history_messages=10, squeeze_whitespace=False
        )
        assert optimized[0].content == content


def _router(tmp_path, seen: dict, **kwargs) -> Router:
    executor = OllamaExecutor(base_url="http://test", default_model="llama3.2:3b", tier="L3")

    async def fake_execute(request: InternalRequest) -> InternalResponse:
        seen["request"] = request.model_copy(deep=True)
        return InternalResponse(
            content="A confident local answer with plenty of length for scoring.",
            model="llama3.2:3b",
            daari_meta=DaariMeta(tier="L3", executor="ollama", provider_id="ollama", latency_ms=1),
        )

    executor.execute = fake_execute  # type: ignore[method-assign]
    return Router(
        cache=ExactCache(str(tmp_path / "l0"), enabled=True),
        semantic_cache=SemanticCache(path=str(tmp_path / "l1"), embedder=NoopEmbedder(), enabled=False),
        ollama=executor,
        metrics=Metrics(),
        **kwargs,
    )


class TestRouterIntegration:
    @pytest.mark.asyncio
    async def test_long_history_trimmed_before_local_model(self, tmp_path):
        seen: dict = {}
        router = _router(tmp_path, seen, context_max_history=4)
        request = InternalRequest(
            messages=[Message(role="system", content="sys"), *_msgs(12)], model="llama3.2:3b"
        )
        await router.route(request)
        assert len(seen["request"].messages) == 5

    @pytest.mark.asyncio
    async def test_agent_tool_history_untouched(self, tmp_path):
        seen: dict = {}
        router = _router(tmp_path, seen, context_max_history=2)
        messages = [
            *_msgs(6),
            Message(
                role="assistant",
                content=None,
                tool_calls=[{"id": "c1", "type": "function", "function": {"name": "f", "arguments": "{}"}}],
            ),
            Message(role="tool", content="result", tool_call_id="c1"),
            Message(role="user", content="continue"),
        ]
        request = InternalRequest(messages=messages, model="llama3.2:3b")
        await router.route(request)
        assert len(seen["request"].messages) == len(messages)

    @pytest.mark.asyncio
    async def test_disabled_optimizer_is_noop(self, tmp_path):
        seen: dict = {}
        router = _router(tmp_path, seen, context_optimizer_enabled=False, context_max_history=2)
        request = InternalRequest(messages=_msgs(10), model="llama3.2:3b")
        await router.route(request)
        assert len(seen["request"].messages) == 10

    @pytest.mark.asyncio
    async def test_trace_records_context_optimized(self, tmp_path):
        seen: dict = {}
        store = TraceStore(path=tmp_path / "traces.sqlite3")
        router = _router(tmp_path, seen, context_max_history=2, trace_store=store)
        request = InternalRequest(messages=_msgs(10), model="llama3.2:3b")
        response = await router.route(request)

        trace = store.get(response.daari_meta.trace_id)
        step = next(s for s in trace["steps"] if s["step"] == "context_optimized")
        assert step["detail"]["chars_after"] < step["detail"]["chars_before"]
