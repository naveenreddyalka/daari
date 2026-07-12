"""Phase D2a: opt-in training example capture (issue #61)."""

from __future__ import annotations

import pytest

from daari.cache.exact import ExactCache
from daari.config.settings import Settings
from daari.gateway.internal import DaariMeta, InternalRequest, InternalResponse, Message
from daari.learning.examples import ExampleStore
from daari.observability.metrics import Metrics
from daari.observability.trace import TraceStore
from daari.router.router import OllamaExecutor, Router


def _store(tmp_path, **kwargs) -> ExampleStore:
    return ExampleStore(str(tmp_path / "examples.sqlite3"), **kwargs)


def _record(store: ExampleStore, trace_id: str = "t1", completion: str = "the answer") -> None:
    store.record(
        trace_id=trace_id,
        category="doc_qa",
        complexity="standard",
        tier="L3",
        model="llama3.2:3b",
        messages=[{"role": "user", "content": "the question"}],
        completion=completion,
    )


class TestExampleStore:
    def test_record_and_read(self, tmp_path):
        store = _store(tmp_path)
        _record(store)

        rows = store.examples(limit=10)
        assert len(rows) == 1
        assert rows[0]["trace_id"] == "t1"
        assert rows[0]["messages"] == [{"role": "user", "content": "the question"}]
        assert rows[0]["completion"] == "the answer"
        assert rows[0]["accepted"] is False

    def test_accept_marks_example(self, tmp_path):
        store = _store(tmp_path)
        _record(store)

        assert store.mark_accepted("t1") is True
        assert store.examples(limit=1)[0]["accepted"] is True
        assert store.mark_accepted("unknown") is False

    def test_reject_deletes_example(self, tmp_path):
        store = _store(tmp_path)
        _record(store)

        assert store.delete("t1") is True
        assert store.examples(limit=10) == []
        assert store.delete("t1") is False

    def test_max_rows_prunes_oldest(self, tmp_path):
        store = _store(tmp_path, max_rows=2)
        for i in range(4):
            _record(store, trace_id=f"t{i}")

        rows = store.examples(limit=10)
        assert {row["trace_id"] for row in rows} == {"t2", "t3"}

    def test_disabled_store_is_noop(self, tmp_path):
        store = _store(tmp_path, enabled=False)
        _record(store)
        assert store.examples(limit=10) == []
        assert store.count() == 0

    def test_clear_wipes_store(self, tmp_path):
        store = _store(tmp_path)
        _record(store, trace_id="t1")
        _record(store, trace_id="t2")

        removed = store.clear()
        assert removed == 2
        assert store.count() == 0

    def test_storage_errors_never_raise(self):
        store = ExampleStore("/dev/null/nope/examples.sqlite3")
        _record(store)
        assert store.examples(limit=10) == []

    def test_settings_defaults(self):
        settings = Settings.model_validate({})
        assert settings.learning.capture_examples is False
        assert settings.learning.examples_max_rows == 5000
        assert "training" in settings.learning.examples_path


class NoopEmbedder:
    async def embed(self, text: str):
        return None


ANSWER = "A generated answer long enough to pass confidence checks."


def _router(tmp_path, *, example_store=None) -> Router:
    from daari.cache.semantic import SemanticCache

    executor = OllamaExecutor(base_url="http://test", default_model="llama3.2:3b", tier="L3")

    async def fake_execute(request: InternalRequest) -> InternalResponse:
        return InternalResponse(
            content=ANSWER,
            model="llama3.2:3b",
            daari_meta=DaariMeta(tier="L3", executor="ollama", provider_id="ollama", latency_ms=5),
        )

    async def fake_stream(request: InternalRequest):
        yield {"message": {"content": ANSWER}, "done": False}
        yield {"message": {"content": ""}, "done": True}

    executor.execute = fake_execute  # type: ignore[method-assign]
    executor.stream = fake_stream  # type: ignore[method-assign]
    return Router(
        cache=ExactCache(str(tmp_path / "l0"), enabled=True),
        semantic_cache=SemanticCache(
            path=str(tmp_path / "l1"), embedder=NoopEmbedder(), enabled=False
        ),
        ollama=executor,
        metrics=Metrics(),
        frontier=None,
        frontier_enabled=False,
        trace_store=TraceStore(tmp_path / "traces.sqlite3"),
        example_store=example_store,
    )


def _request(text: str) -> InternalRequest:
    return InternalRequest(messages=[Message(role="user", content=text)], model="llama3.2:3b")


class TestRouterCapture:
    @pytest.mark.asyncio
    async def test_route_captures_example(self, tmp_path):
        store = _store(tmp_path)
        router = _router(tmp_path, example_store=store)
        response = await router.route(_request("what is a mutex used for"))

        rows = store.examples(limit=5)
        assert len(rows) == 1
        assert rows[0]["trace_id"] == response.daari_meta.trace_id
        assert rows[0]["completion"] == ANSWER
        assert rows[0]["messages"][-1]["content"] == "what is a mutex used for"

    @pytest.mark.asyncio
    async def test_cache_hit_not_captured(self, tmp_path):
        store = _store(tmp_path)
        router = _router(tmp_path, example_store=store)
        await router.route(_request("repeat question"))
        await router.route(_request("repeat question"))  # L0 hit

        assert store.count() == 1

    @pytest.mark.asyncio
    async def test_agent_flow_not_captured(self, tmp_path):
        store = _store(tmp_path)
        router = _router(tmp_path, example_store=store)
        request = InternalRequest(
            messages=[
                Message(role="user", content="run the tool"),
                Message(
                    role="assistant",
                    tool_calls=[{"id": "c1", "function": {"name": "f", "arguments": "{}"}}],
                ),
                Message(role="tool", content="tool output"),
            ],
            model="llama3.2:3b",
        )
        await router.route(request)

        assert store.count() == 0

    @pytest.mark.asyncio
    async def test_stream_captures_example(self, tmp_path):
        store = _store(tmp_path)
        router = _router(tmp_path, example_store=store)
        async for _chunk in router.stream_openai_chunks(_request("stream capture check")):
            pass

        rows = store.examples(limit=5)
        assert len(rows) == 1
        assert rows[0]["completion"] == ANSWER

    @pytest.mark.asyncio
    async def test_no_store_captures_nothing(self, tmp_path):
        router = _router(tmp_path, example_store=None)
        response = await router.route(_request("capture disabled"))
        assert response.daari_meta.tier == "L3"
