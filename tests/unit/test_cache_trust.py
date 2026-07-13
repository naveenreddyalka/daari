"""Train 1 cache trust: normalization, diversity, shadow sampling (issue #69)."""

from __future__ import annotations

import asyncio

import pytest

from daari.cache.exact import ExactCache
from daari.cache.normalize import normalize_for_embedding
from daari.cache.semantic import SemanticCache
from daari.config.settings import Settings
from daari.gateway.internal import DaariMeta, InternalRequest, InternalResponse, Message
from daari.learning.feedback import FeedbackStore
from daari.observability.metrics import Metrics
from daari.observability.trace import TraceStore
from daari.router.router import OllamaExecutor, Router


class TestNormalizeForEmbedding:
    def test_squeezes_whitespace(self):
        assert normalize_for_embedding("hello    world\n\n\n  x") == "hello world x"

    def test_strips_code_fence_markers_keeps_code(self):
        text = "explain this\n```python\nx = 1\n```"
        normalized = normalize_for_embedding(text)
        assert "```" not in normalized
        assert "x = 1" in normalized

    def test_drops_scaffolding_only_lines(self):
        text = '{\n  "name": "value",\n}\n[\n]\nreal question here'
        normalized = normalize_for_embedding(text)
        assert "real question here" in normalized
        assert "{" not in normalized.split("real")[0].strip() or True
        # Scaffolding-only lines ({, }, [, ]) must be gone entirely.
        assert "[" not in normalized
        assert normalized.count("{") == 0

    def test_json_values_survive(self):
        text = '{"task": "translate to french", "text": "good morning"}'
        normalized = normalize_for_embedding(text)
        assert "translate to french" in normalized
        assert "good morning" in normalized

    def test_two_templated_requests_diverge_after_normalization(self):
        a = '{\n  "op": "translate",\n  "payload": "hello there friend"\n}'
        b = '{\n  "op": "translate",\n  "payload": "goodbye cruel world"\n}'
        assert normalize_for_embedding(a) != normalize_for_embedding(b)


class RecordingEmbedder:
    """Maps distinct texts to orthogonal vectors; records what was embedded."""

    def __init__(self):
        self.seen: list[str] = []
        self._known: dict[str, list[float]] = {}

    async def embed(self, text: str):
        self.seen.append(text)
        if text not in self._known:
            index = len(self._known)
            vector = [0.0] * 16
            vector[index % 16] = 1.0
            self._known[text] = vector
        return list(self._known[text])


def _request(text: str) -> InternalRequest:
    return InternalRequest(messages=[Message(role="user", content=text)], model="daari")


def _response(content: str) -> InternalResponse:
    return InternalResponse(
        content=content,
        model="llama3.2:3b",
        daari_meta=DaariMeta(tier="L3", executor="ollama", provider_id="ollama", latency_ms=1),
    )


class TestSemanticCacheNormalization:
    @pytest.mark.asyncio
    async def test_embeds_normalized_text_when_enabled(self, tmp_path):
        embedder = RecordingEmbedder()
        cache = SemanticCache(
            str(tmp_path / "l1"), embedder, enabled=True, normalize_inputs=True
        )
        await cache.put(_request("hello    world"), _response("answer"))

        assert all("  " not in text for text in embedder.seen)

    @pytest.mark.asyncio
    async def test_raw_text_when_disabled(self, tmp_path):
        embedder = RecordingEmbedder()
        cache = SemanticCache(
            str(tmp_path / "l1"), embedder, enabled=True, normalize_inputs=False
        )
        await cache.put(_request("hello    world"), _response("answer"))

        assert any("hello    world" in text for text in embedder.seen)

    def test_settings_defaults(self):
        settings = Settings.model_validate({})
        assert settings.cache.l1.normalize_inputs is True
        assert settings.cache.l1.shadow_sample_rate == 0.05


class TestDiversityStats:
    @pytest.mark.asyncio
    async def test_flags_single_answer_category(self, tmp_path):
        embedder = RecordingEmbedder()
        cache = SemanticCache(str(tmp_path / "l1"), embedder, enabled=True)
        # doc_qa: 3 distinct prompts, all cached with the same answer.
        for i, text in enumerate(
            ["what is a mutex?", "what is a lock?", "what is a futex?"]
        ):
            await cache.put(_request(text), _response("It synchronizes threads."))
        await cache.put(
            _request("what's a semaphore?"), _response("A counter-based primitive.")
        )

        stats = cache.diversity_stats()
        doc_qa = stats["doc_qa"]
        assert doc_qa["entries"] == 4
        assert doc_qa["unique_answers"] == 2
        assert doc_qa["ratio"] == 0.5

    @pytest.mark.asyncio
    async def test_empty_cache(self, tmp_path):
        cache = SemanticCache(str(tmp_path / "l1"), RecordingEmbedder(), enabled=True)
        assert cache.diversity_stats() == {}


class TestShadowStore:
    def test_record_and_aggregate(self, tmp_path):
        store = FeedbackStore(str(tmp_path / "feedback.sqlite3"))
        for i in range(8):
            store.record_shadow(category="doc_qa", similarity=0.9, agreed=True)
        for i in range(2):
            store.record_shadow(category="doc_qa", similarity=0.3, agreed=False)

        stats = store.shadow_stats(days=7)
        assert stats["doc_qa"]["samples"] == 10
        assert stats["doc_qa"]["disagreements"] == 2
        assert stats["doc_qa"]["false_hit_rate"] == 0.2

    def test_empty(self, tmp_path):
        store = FeedbackStore(str(tmp_path / "feedback.sqlite3"))
        assert store.shadow_stats(days=7) == {}


class HitEmbedder:
    """Every text maps to the same vector — everything is similarity 1.0."""

    async def embed(self, text: str):
        return [1.0, 0.0]


def _router(tmp_path, *, shadow_rate=0.0, rng=None, feedback=None) -> Router:
    executor = OllamaExecutor(base_url="http://test", default_model="llama3.2:3b", tier="L3")

    async def fake_execute(request: InternalRequest) -> InternalResponse:
        return _response("A freshly generated model answer for comparison.")

    executor.execute = fake_execute  # type: ignore[method-assign]
    return Router(
        cache=ExactCache(str(tmp_path / "l0"), enabled=False),
        semantic_cache=SemanticCache(str(tmp_path / "l1"), HitEmbedder(), enabled=True),
        ollama=executor,
        metrics=Metrics(),
        frontier=None,
        frontier_enabled=False,
        trace_store=TraceStore(tmp_path / "traces.sqlite3"),
        feedback_store=feedback,
        l1_shadow_sample_rate=shadow_rate,
        shadow_rng=rng,
    )


class TestShadowSampling:
    @pytest.mark.asyncio
    async def test_sampled_l1_hit_records_shadow_check(self, tmp_path):
        feedback = FeedbackStore(str(tmp_path / "feedback.sqlite3"))
        router = _router(tmp_path, shadow_rate=1.0, feedback=feedback)
        await router.semantic_cache.put(
            _request("what is a mutex?"), _response("Cached mutex answer.")
        )

        response = await router.route(_request("what is a lock?"))
        assert response.daari_meta.tier == "L1"
        await asyncio.gather(*router._shadow_tasks)

        stats = feedback.shadow_stats(days=1)
        assert stats["doc_qa"]["samples"] == 1

    @pytest.mark.asyncio
    async def test_zero_rate_never_samples(self, tmp_path):
        feedback = FeedbackStore(str(tmp_path / "feedback.sqlite3"))
        router = _router(tmp_path, shadow_rate=0.0, feedback=feedback)
        await router.semantic_cache.put(
            _request("what is a mutex?"), _response("Cached mutex answer.")
        )

        await router.route(_request("what is a lock?"))
        await asyncio.gather(*router._shadow_tasks)

        assert feedback.shadow_stats(days=1) == {}

    @pytest.mark.asyncio
    async def test_shadow_failure_never_breaks_serving(self, tmp_path):
        feedback = FeedbackStore(str(tmp_path / "feedback.sqlite3"))
        router = _router(tmp_path, shadow_rate=1.0, feedback=feedback)

        async def boom(request):
            raise RuntimeError("model down")

        router.ollama_l3.execute = boom  # type: ignore[method-assign]
        await router.semantic_cache.put(
            _request("what is a mutex?"), _response("Cached mutex answer.")
        )

        response = await router.route(_request("what is a lock?"))
        assert response.daari_meta.tier == "L1"
        await asyncio.gather(*router._shadow_tasks)


class TestL1ThresholdTuning:
    @pytest.mark.asyncio
    async def test_high_false_hit_rate_raises_threshold(self, tmp_path):
        feedback = FeedbackStore(str(tmp_path / "feedback.sqlite3"))
        for _ in range(25):
            feedback.record_shadow(category="doc_qa", similarity=0.2, agreed=False)
        router = _router(tmp_path, feedback=feedback)

        base = router.semantic_cache.similarity_threshold
        tuned = router._l1_threshold_for_category("doc_qa")
        assert tuned == pytest.approx(min(0.99, base + 0.02))

    @pytest.mark.asyncio
    async def test_low_false_hit_rate_keeps_base(self, tmp_path):
        feedback = FeedbackStore(str(tmp_path / "feedback.sqlite3"))
        for _ in range(25):
            feedback.record_shadow(category="doc_qa", similarity=0.95, agreed=True)
        router = _router(tmp_path, feedback=feedback)

        assert router._l1_threshold_for_category("doc_qa") == pytest.approx(
            router.semantic_cache.similarity_threshold
        )

    @pytest.mark.asyncio
    async def test_thin_evidence_keeps_base(self, tmp_path):
        feedback = FeedbackStore(str(tmp_path / "feedback.sqlite3"))
        for _ in range(5):
            feedback.record_shadow(category="doc_qa", similarity=0.2, agreed=False)
        router = _router(tmp_path, feedback=feedback)

        assert router._l1_threshold_for_category("doc_qa") == pytest.approx(
            router.semantic_cache.similarity_threshold
        )
