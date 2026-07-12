"""Phase D1c: per-category confidence thresholds from outcomes (issue #55)."""

from __future__ import annotations

import pytest

from daari.cache.exact import ExactCache
from daari.config.settings import Settings
from daari.gateway.internal import DaariMeta, InternalRequest, InternalResponse, Message
from daari.learning.feedback import FeedbackStore
from daari.learning.tuner import RoutingTuner
from daari.observability.metrics import Metrics
from daari.observability.trace import TraceStore
from daari.router.router import OllamaExecutor, Router


def _store(tmp_path) -> FeedbackStore:
    return FeedbackStore(str(tmp_path / "feedback.sqlite3"))


def _seed(store: FeedbackStore, *, category: str, count: int, escalated: int = 0,
          rejects: int = 0, accepts: int = 0, tier: str = "L3") -> None:
    for i in range(count):
        trace_id = f"{category}-{tier}-{i}"
        store.record_outcome(
            trace_id=trace_id, category=category, complexity="standard",
            tier=tier, confidence=0.8, escalated=i < escalated, latency_ms=50,
        )
        if i < rejects:
            store.record_signal(trace_id, "reject")
        elif i < rejects + accepts:
            store.record_signal(trace_id, "accept")


def _tuner(store: FeedbackStore, **kwargs) -> RoutingTuner:
    kwargs.setdefault("base_threshold", 0.7)
    kwargs.setdefault("min_samples", 50)
    kwargs.setdefault("refresh_seconds", 0.0)
    return RoutingTuner(store, **kwargs)


class TestTunerDirection:
    def test_reliable_category_lowers_threshold(self, tmp_path):
        store = _store(tmp_path)
        _seed(store, category="doc_qa", count=60, escalated=1, accepts=10)

        assert _tuner(store).threshold_for("doc_qa") == pytest.approx(0.65)

    def test_weak_category_raises_threshold(self, tmp_path):
        store = _store(tmp_path)
        _seed(store, category="code_gen", count=60, escalated=25)

        assert _tuner(store).threshold_for("code_gen") == pytest.approx(0.75)

    def test_reject_heavy_category_raises_threshold(self, tmp_path):
        store = _store(tmp_path)
        _seed(store, category="chat", count=60, escalated=0, rejects=15)

        assert _tuner(store).threshold_for("chat") == pytest.approx(0.75)

    def test_middling_evidence_keeps_base(self, tmp_path):
        store = _store(tmp_path)
        _seed(store, category="doc_qa", count=60, escalated=9)  # 15% — in the middle band

        assert _tuner(store).threshold_for("doc_qa") == pytest.approx(0.7)


class TestTunerGuards:
    def test_below_min_samples_keeps_base(self, tmp_path):
        store = _store(tmp_path)
        _seed(store, category="doc_qa", count=10, escalated=0, accepts=5)

        assert _tuner(store).threshold_for("doc_qa") == pytest.approx(0.7)

    def test_unknown_category_keeps_base(self, tmp_path):
        assert _tuner(_store(tmp_path)).threshold_for("mystery") == pytest.approx(0.7)

    def test_clamped_to_bounds(self, tmp_path):
        store = _store(tmp_path)
        _seed(store, category="doc_qa", count=60, escalated=0, accepts=20)
        _seed(store, category="code_gen", count=60, escalated=40)

        low = _tuner(store, base_threshold=0.52).threshold_for("doc_qa")
        high = _tuner(store, base_threshold=0.88).threshold_for("code_gen")
        assert low == pytest.approx(0.5)
        assert high == pytest.approx(0.9)

    def test_store_errors_keep_base(self, tmp_path):
        broken = FeedbackStore("/dev/null/nope/feedback.sqlite3")
        assert _tuner(broken).threshold_for("doc_qa") == pytest.approx(0.7)

    def test_settings_defaults(self):
        settings = Settings.model_validate({})
        assert settings.learning.auto_tune is False
        assert settings.learning.tuner_min_samples == 50


class NoopEmbedder:
    async def embed(self, text: str):
        return None


def _router(tmp_path, *, tuner=None) -> Router:
    from daari.cache.semantic import SemanticCache

    executor = OllamaExecutor(base_url="http://test", default_model="llama3.2:3b", tier="L3")

    async def fake_execute(request: InternalRequest) -> InternalResponse:
        return InternalResponse(
            content="A locally generated answer that is decent but not perfect.",
            model="llama3.2:3b",
            daari_meta=DaariMeta(tier="L3", executor="ollama", provider_id="ollama", latency_ms=5),
        )

    executor.execute = fake_execute  # type: ignore[method-assign]
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
        tuner=tuner,
    )


def _request(text: str, **meta) -> InternalRequest:
    request = InternalRequest(messages=[Message(role="user", content=text)], model="llama3.2:3b")
    for key, value in meta.items():
        setattr(request.meta, key, value)
    return request


# Starts with "what" and has no code tokens — categorizes as doc_qa.
PROMPT = "what is the overall purpose of this project according to its documentation"


class TestRouterIntegration:
    @pytest.mark.asyncio
    async def test_tuned_lower_threshold_avoids_escalation_warning(self, tmp_path, monkeypatch):
        # Graded confidence 0.68: below base 0.7, above tuned 0.65.
        monkeypatch.setattr("daari.router.router.score_l3_confidence", lambda content: 0.68)
        store = _store(tmp_path)
        _seed(store, category="doc_qa", count=60, escalated=1, accepts=10)

        tuned = await _router(tmp_path, tuner=_tuner(store)).route(_request(PROMPT))
        base = await _router(tmp_path, tuner=None).route(_request(PROMPT, no_cache=True))

        assert tuned.daari_meta.warning is None, "tuned threshold should accept 0.68"
        assert base.daari_meta.warning == "below_confidence_threshold"

    @pytest.mark.asyncio
    async def test_tier_override_ignores_tuner(self, tmp_path, monkeypatch):
        monkeypatch.setattr("daari.router.router.score_l3_confidence", lambda content: 0.68)
        store = _store(tmp_path)
        _seed(store, category="doc_qa", count=60, escalated=1, accepts=10)

        router = _router(tmp_path, tuner=_tuner(store))
        response = await router.route(_request(PROMPT, tier_override="L3"))

        assert response.daari_meta.warning == "below_confidence_threshold"

    @pytest.mark.asyncio
    async def test_tuner_step_recorded_in_trace(self, tmp_path, monkeypatch):
        monkeypatch.setattr("daari.router.router.score_l3_confidence", lambda content: 0.68)
        store = _store(tmp_path)
        _seed(store, category="doc_qa", count=60, escalated=1, accepts=10)

        router = _router(tmp_path, tuner=_tuner(store))
        response = await router.route(_request(PROMPT))

        trace = router.trace_store.get(response.daari_meta.trace_id)
        steps = [step["step"] for step in trace["steps"]]
        assert "tuner" in steps
        tuner_step = next(step for step in trace["steps"] if step["step"] == "tuner")
        assert tuner_step["detail"]["base"] == pytest.approx(0.7)
        assert tuner_step["detail"]["tuned"] == pytest.approx(0.65)

    @pytest.mark.asyncio
    async def test_default_off_no_tuner_no_trace_step(self, tmp_path):
        router = _router(tmp_path, tuner=None)
        response = await router.route(_request(PROMPT))

        trace = router.trace_store.get(response.daari_meta.trace_id)
        assert all(step["step"] != "tuner" for step in trace["steps"])
        assert response.daari_meta.warning is None
