"""Train 4 learned routing: training, prediction, floor fallback (issue #73)."""

from __future__ import annotations

import pytest

from daari.cache.exact import ExactCache
from daari.cache.semantic import SemanticCache
from daari.config.settings import Settings
from daari.gateway.internal import DaariMeta, InternalRequest, InternalResponse, Message
from daari.learning.examples import ExampleStore
from daari.learning.router_model import (
    LearnedRouter,
    RouterTrainingError,
    train_router,
)
from daari.observability.metrics import Metrics
from daari.observability.trace import TraceStore
from daari.router.router import OllamaExecutor, Router


class AxisEmbedder:
    """'widget' words -> x axis, 'banana' words -> y axis; neutral otherwise.

    Deliberately keyed on words the keyword heuristic does NOT know, so tests
    can construct prompts where the heuristic and the embedding disagree.
    """

    async def embed(self, text: str):
        lower = text.lower()
        code = sum(word in lower for word in ("widget", "gizmo"))
        doc = sum(word in lower for word in ("banana", "smoothie"))
        if code == 0 and doc == 0:
            return [0.7071, 0.7071]
        total = float(code + doc)
        return [code / total, doc / total]


def _seed_examples(store: ExampleStore, count_per_category: int = 6) -> None:
    for i in range(count_per_category):
        store.record(
            trace_id=f"code-{i}",
            category="code_gen",
            complexity="standard",
            tier="L3",
            model="m",
            messages=[{"role": "user", "content": f"please handle the widget gizmo case {i}"}],
            completion="done",
        )
        store.record(
            trace_id=f"doc-{i}",
            category="doc_qa",
            complexity="trivial",
            tier="L3",
            model="m",
            messages=[{"role": "user", "content": f"tell me about banana smoothie number {i}"}],
            completion="answered",
        )


class TestTraining:
    @pytest.mark.asyncio
    async def test_trains_centroids_and_saves(self, tmp_path):
        store = ExampleStore(tmp_path / "examples.sqlite3")
        _seed_examples(store)
        out = tmp_path / "router-model.json"

        result = await train_router(store, AxisEmbedder(), out_path=out, min_samples=10)

        assert result["samples"] == 12
        assert set(result["categories"]) == {"code_gen", "doc_qa"}
        assert out.exists()

    @pytest.mark.asyncio
    async def test_refuses_below_sample_floor(self, tmp_path):
        store = ExampleStore(tmp_path / "examples.sqlite3")
        _seed_examples(store, count_per_category=2)

        with pytest.raises(RouterTrainingError):
            await train_router(
                store, AxisEmbedder(), out_path=tmp_path / "m.json", min_samples=10
            )


class TestPrediction:
    async def _trained(self, tmp_path) -> LearnedRouter:
        store = ExampleStore(tmp_path / "examples.sqlite3")
        _seed_examples(store)
        out = tmp_path / "router-model.json"
        await train_router(store, AxisEmbedder(), out_path=out, min_samples=10)
        return LearnedRouter(out, min_samples=10)

    @pytest.mark.asyncio
    async def test_confident_prediction(self, tmp_path):
        router = await self._trained(tmp_path)
        embedding = await AxisEmbedder().embed("sort out the widget gizmo")
        prediction = router.predict(embedding)
        assert prediction is not None
        assert prediction[0] == "code_gen"
        assert prediction[1] > 0.9

    @pytest.mark.asyncio
    async def test_ambiguous_prompt_returns_none(self, tmp_path):
        router = await self._trained(tmp_path)
        # Neutral text embeds equidistant from both centroids.
        embedding = await AxisEmbedder().embed("hello there")
        assert router.predict(embedding) is None

    def test_missing_model_never_guesses(self, tmp_path):
        router = LearnedRouter(tmp_path / "missing.json", min_samples=10)
        assert router.available is False
        assert router.predict([1.0, 0.0]) is None

    @pytest.mark.asyncio
    async def test_sample_floor_gates_predictions(self, tmp_path):
        store = ExampleStore(tmp_path / "examples.sqlite3")
        _seed_examples(store)  # 12 samples
        out = tmp_path / "router-model.json"
        await train_router(store, AxisEmbedder(), out_path=out, min_samples=10)

        gated = LearnedRouter(out, min_samples=200)
        assert gated.available is False
        assert gated.predict([1.0, 0.0]) is None

    def test_settings_defaults(self):
        settings = Settings.model_validate({})
        assert settings.routing.learned_router is False
        assert settings.learning.router_min_samples == 200


class TestRouterIntegration:
    def _router(self, tmp_path, learned) -> Router:
        executor = OllamaExecutor(base_url="http://test", default_model="llama3.2:3b", tier="L3")

        async def fake_execute(request: InternalRequest) -> InternalResponse:
            return InternalResponse(
                content="A long, thorough, and complete answer to the question posed.",
                model="llama3.2:3b",
                daari_meta=DaariMeta(
                    tier="L3", executor="ollama", provider_id="ollama", latency_ms=1
                ),
            )

        executor.execute = fake_execute  # type: ignore[method-assign]
        return Router(
            cache=ExactCache(str(tmp_path / "l0"), enabled=False),
            semantic_cache=SemanticCache(
                str(tmp_path / "l1"), AxisEmbedder(), enabled=False
            ),
            ollama=executor,
            metrics=Metrics(),
            frontier=None,
            frontier_enabled=False,
            trace_store=TraceStore(tmp_path / "traces.sqlite3"),
            learned_router=learned,
        )

    @pytest.mark.asyncio
    async def test_learned_category_overrides_heuristic(self, tmp_path):
        store = ExampleStore(tmp_path / "examples.sqlite3")
        _seed_examples(store)
        out = tmp_path / "router-model.json"
        await train_router(store, AxisEmbedder(), out_path=out, min_samples=10)
        router = self._router(tmp_path, LearnedRouter(out, min_samples=10))

        # Heuristically this is plain chat, but embeddings match code_gen.
        response = await router.route(
            InternalRequest(
                messages=[
                    Message(role="user", content="please sort out the widget gizmo thing")
                ],
                model="daari",
            )
        )

        trace = router.trace_store.get(response.daari_meta.trace_id)
        steps = {step["step"]: step for step in trace["steps"]}
        assert "learned_route" in steps
        assert steps["learned_route"]["detail"]["category"] == "code_gen"
        assert response.daari_meta.task_type == "code_gen"

    @pytest.mark.asyncio
    async def test_no_model_keeps_heuristics(self, tmp_path):
        router = self._router(
            tmp_path, LearnedRouter(tmp_path / "missing.json", min_samples=10)
        )
        response = await router.route(
            InternalRequest(
                messages=[Message(role="user", content="what is the documentation for x")],
                model="daari",
            )
        )
        trace = router.trace_store.get(response.daari_meta.trace_id)
        step_names = [step["step"] for step in trace["steps"]]
        assert "learned_route" not in step_names
        assert response.daari_meta.task_type == "doc_qa"
