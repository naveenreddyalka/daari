"""Phase D1a: outcome store + implicit capture + explicit feedback (issue #53)."""

from __future__ import annotations

import pytest

from daari.cache.exact import ExactCache
from daari.config.settings import Settings
from daari.gateway.internal import DaariMeta, InternalRequest, InternalResponse, Message
from daari.learning.feedback import FeedbackStore
from daari.observability.metrics import Metrics
from daari.observability.trace import TraceStore
from daari.router.router import OllamaExecutor, Router


def _store(tmp_path, **kwargs) -> FeedbackStore:
    return FeedbackStore(str(tmp_path / "feedback.sqlite3"), **kwargs)


class TestFeedbackStore:
    def test_record_and_read_outcome(self, tmp_path):
        store = _store(tmp_path)
        store.record_outcome(
            trace_id="t1",
            category="code_gen",
            complexity="standard",
            tier="L3",
            confidence=0.9,
            escalated=False,
            latency_ms=120,
        )

        rows = store.outcomes(limit=10)
        assert len(rows) == 1
        row = rows[0]
        assert row["trace_id"] == "t1"
        assert row["category"] == "code_gen"
        assert row["tier"] == "L3"
        assert row["escalated"] is False
        assert row["signal"] is None

    def test_explicit_signal_joins_by_trace_id(self, tmp_path):
        store = _store(tmp_path)
        store.record_outcome(
            trace_id="t2", category="doc_qa", complexity="trivial",
            tier="L3", confidence=0.8, escalated=False, latency_ms=50,
        )

        assert store.record_signal("t2", "accept") is True
        assert store.outcomes(limit=1)[0]["signal"] == "accept"

    def test_unknown_trace_signal_returns_false(self, tmp_path):
        store = _store(tmp_path)
        assert store.record_signal("nope", "reject") is False

    def test_invalid_signal_rejected(self, tmp_path):
        store = _store(tmp_path)
        store.record_outcome(
            trace_id="t3", category="chat", complexity="trivial",
            tier="L3", confidence=None, escalated=False, latency_ms=5,
        )
        with pytest.raises(ValueError):
            store.record_signal("t3", "maybe")

    def test_max_rows_prunes_oldest(self, tmp_path):
        store = _store(tmp_path, max_rows=3)
        for i in range(5):
            store.record_outcome(
                trace_id=f"t{i}", category="chat", complexity="trivial",
                tier="L3", confidence=0.5, escalated=False, latency_ms=1,
            )

        rows = store.outcomes(limit=10)
        assert len(rows) == 3
        assert {row["trace_id"] for row in rows} == {"t2", "t3", "t4"}

    def test_disabled_store_is_noop(self, tmp_path):
        store = _store(tmp_path, enabled=False)
        store.record_outcome(
            trace_id="t1", category="chat", complexity="trivial",
            tier="L3", confidence=0.5, escalated=False, latency_ms=1,
        )
        assert store.outcomes(limit=10) == []
        assert store.record_signal("t1", "accept") is False

    def test_storage_errors_never_raise(self, tmp_path):
        store = FeedbackStore("/dev/null/nope/feedback.sqlite3")
        store.record_outcome(
            trace_id="t1", category="chat", complexity="trivial",
            tier="L3", confidence=0.5, escalated=False, latency_ms=1,
        )
        assert store.outcomes(limit=10) == []

    def test_settings_defaults(self):
        settings = Settings.model_validate({})
        assert settings.learning.enabled is True
        assert settings.learning.max_rows == 20000
        assert "feedback" in settings.learning.path


class NoopEmbedder:
    async def embed(self, text: str):
        return None


def _router(tmp_path, *, content="A confident local answer with plenty of length.") -> Router:
    from daari.cache.semantic import SemanticCache

    executor = OllamaExecutor(base_url="http://test", default_model="llama3.2:3b", tier="L3")

    async def fake_execute(request: InternalRequest) -> InternalResponse:
        return InternalResponse(
            content=content,
            model="llama3.2:3b",
            daari_meta=DaariMeta(tier="L3", executor="ollama", provider_id="ollama", latency_ms=7),
        )

    async def fake_stream(request: InternalRequest):
        yield {"message": {"content": content}, "done": False}
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
        feedback_store=_store(tmp_path),
    )


def _request(text: str) -> InternalRequest:
    return InternalRequest(messages=[Message(role="user", content=text)], model="llama3.2:3b")


class TestImplicitCapture:
    @pytest.mark.asyncio
    async def test_model_response_records_outcome(self, tmp_path):
        router = _router(tmp_path)
        response = await router.route(_request("write a haiku about caching"))

        rows = router.feedback_store.outcomes(limit=5)
        assert len(rows) == 1
        assert rows[0]["tier"] == "L3"
        assert rows[0]["trace_id"] == response.daari_meta.trace_id
        assert rows[0]["escalated"] is False

    @pytest.mark.asyncio
    async def test_cache_hit_not_recorded(self, tmp_path):
        router = _router(tmp_path)
        await router.route(_request("same question"))
        await router.route(_request("same question"))  # L0 hit

        rows = router.feedback_store.outcomes(limit=5)
        assert len(rows) == 1, "cache hits must not create outcome rows"

    @pytest.mark.asyncio
    async def test_stream_records_outcome(self, tmp_path):
        router = _router(tmp_path)
        async for _chunk in router.stream_openai_chunks(_request("stream me a poem")):
            pass

        rows = router.feedback_store.outcomes(limit=5)
        assert len(rows) == 1
        assert rows[0]["tier"] == "L3"
        assert rows[0]["trace_id"] is not None

    @pytest.mark.asyncio
    async def test_no_store_is_fine(self, tmp_path):
        router = _router(tmp_path)
        router.feedback_store = None
        response = await router.route(_request("no store configured"))
        assert response.daari_meta.tier == "L3"
