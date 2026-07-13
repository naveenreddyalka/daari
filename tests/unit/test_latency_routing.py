"""Train 3 latency-aware routing: profiling, budgets, warm awareness (issue #72)."""

from __future__ import annotations

import json

import httpx
import pytest

from daari.cache.exact import ExactCache
from daari.cache.semantic import SemanticCache
from daari.config.settings import Settings
from daari.gateway.internal import InternalRequest, Message, RequestMeta
from daari.observability.metrics import Metrics
from daari.router.model_profile import (
    ModelProfileStore,
    WarmModelTracker,
    benchmark_model,
)
from daari.router.router import OllamaExecutor, Router


class NullEmbedder:
    async def embed(self, text: str):
        return None


def _router(tmp_path, **kwargs) -> Router:
    return Router(
        cache=ExactCache(str(tmp_path / "l0"), enabled=False),
        semantic_cache=SemanticCache(str(tmp_path / "l1"), NullEmbedder(), enabled=False),
        ollama=OllamaExecutor(base_url="http://test", default_model="llama3.2:3b", tier="L3"),
        ollama_l4=OllamaExecutor(base_url="http://test", default_model="llama3.1:8b", tier="L4"),
        ollama_l5=OllamaExecutor(base_url="http://test", default_model="qwen2.5:14b", tier="L5"),
        metrics=Metrics(),
        frontier=None,
        frontier_enabled=False,
        **kwargs,
    )


def _request(text: str, *, latency_budget_ms: int | None = None) -> InternalRequest:
    return InternalRequest(
        messages=[Message(role="user", content=text)],
        model="daari",
        meta=RequestMeta(latency_budget_ms=latency_budget_ms),
    )


class TestModelProfileStore:
    def test_round_trip_and_latency_lookup(self, tmp_path):
        store = ModelProfileStore(tmp_path / "models.json")
        store.save({"llama3.2:3b": {"latency_ms": 800.0, "tokens_per_second": 40.0}})
        assert store.latency_ms_for("llama3.2:3b") == 800.0
        assert store.latency_ms_for("unknown") is None

    def test_missing_file_is_empty(self, tmp_path):
        store = ModelProfileStore(tmp_path / "nope.json")
        assert store.load() == {}


class TestBenchmark:
    @pytest.mark.asyncio
    async def test_benchmark_parses_ollama_timings(self):
        def handler(request: httpx.Request) -> httpx.Response:
            assert json.loads(request.content)["model"] == "llama3.2:3b"
            return httpx.Response(
                200,
                json={
                    "response": "4.",
                    "eval_count": 10,
                    "eval_duration": 500_000_000,  # 0.5s -> 20 tok/s
                    "load_duration": 1_200_000_000,
                },
            )

        entry = await benchmark_model(
            "http://test", "llama3.2:3b", transport=httpx.MockTransport(handler)
        )
        assert entry["tokens_per_second"] == 20.0
        assert entry["load_ms"] == 1200.0
        assert entry["latency_ms"] > 0

    @pytest.mark.asyncio
    async def test_benchmark_failure_returns_none(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(500)

        entry = await benchmark_model(
            "http://test", "gone", transport=httpx.MockTransport(handler)
        )
        assert entry is None


class TestLatencyBudget:
    def _profiled_router(self, tmp_path, **kwargs) -> Router:
        store = ModelProfileStore(tmp_path / "models.json")
        store.save(
            {
                "llama3.2:3b": {"latency_ms": 700.0},
                "llama3.1:8b": {"latency_ms": 2500.0},
                "qwen2.5:14b": {"latency_ms": 9000.0},
            }
        )
        return _router(tmp_path, model_profile_store=store, **kwargs)

    def test_over_budget_tier_steps_down(self, tmp_path):
        router = self._profiled_router(tmp_path, latency_budget_ms=1000)
        # 300 words -> length heuristic says L4 (2500ms), budget forces L3.
        long_prompt = " ".join(["word"] * 300)
        assert router._choose_initial_tier(_request(long_prompt)) == "L3"

    def test_within_budget_keeps_choice(self, tmp_path):
        router = self._profiled_router(tmp_path, latency_budget_ms=5000)
        long_prompt = " ".join(["word"] * 300)
        assert router._choose_initial_tier(_request(long_prompt)) == "L4"

    def test_header_budget_wins_over_global(self, tmp_path):
        router = self._profiled_router(tmp_path, latency_budget_ms=5000)
        long_prompt = " ".join(["word"] * 300)
        request = _request(long_prompt, latency_budget_ms=1000)
        assert router._choose_initial_tier(request) == "L3"

    def test_no_budget_is_noop(self, tmp_path):
        router = self._profiled_router(tmp_path)
        long_prompt = " ".join(["word"] * 300)
        assert router._choose_initial_tier(_request(long_prompt)) == "L4"

    def test_unprofiled_model_is_noop(self, tmp_path):
        router = _router(
            tmp_path,
            model_profile_store=ModelProfileStore(tmp_path / "empty.json"),
            latency_budget_ms=100,
        )
        long_prompt = " ".join(["word"] * 300)
        assert router._choose_initial_tier(_request(long_prompt)) == "L4"

    def test_tier_override_beats_budget(self, tmp_path):
        router = self._profiled_router(tmp_path, latency_budget_ms=100)
        request = _request("hi")
        request.meta.tier_override = "L5"
        assert router._choose_initial_tier(request) == "L5"

    def test_category_policy_budget(self, tmp_path):
        router = self._profiled_router(
            tmp_path,
            category_policies={"doc_qa": {"latency_budget_ms": 1000}},
        )
        # doc_qa category, 300 words -> L4 heuristic, category budget -> L3.
        long_prompt = "what is " + " ".join(["word"] * 300)
        assert router._choose_initial_tier(_request(long_prompt)) == "L3"

    def test_settings_defaults(self):
        settings = Settings.model_validate({})
        assert settings.routing.latency_budget_ms == 0
        assert settings.routing.warm_model_preference is True


class TestWarmModelTracker:
    @pytest.mark.asyncio
    async def test_refresh_parses_ps_and_caches(self):
        calls = {"n": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            calls["n"] += 1
            return httpx.Response(200, json={"models": [{"name": "llama3.2:3b"}]})

        fake_now = {"t": 0.0}
        tracker = WarmModelTracker(
            "http://test",
            ttl_seconds=5.0,
            transport=httpx.MockTransport(handler),
            clock=lambda: fake_now["t"],
        )
        assert await tracker.refresh() == {"llama3.2:3b"}
        assert await tracker.refresh() == {"llama3.2:3b"}
        assert calls["n"] == 1, "second refresh inside TTL must not re-fetch"

        fake_now["t"] = 6.0
        await tracker.refresh()
        assert calls["n"] == 2

    @pytest.mark.asyncio
    async def test_unreachable_ollama_gives_empty_set(self):
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("down")

        tracker = WarmModelTracker("http://test", transport=httpx.MockTransport(handler))
        assert await tracker.refresh() == set()

    def test_warm_model_breaks_weight_tie(self, tmp_path):
        # Weights make L3 and L4 exactly tied; warm L4 must win.
        router = _router(
            tmp_path,
            model_weights={
                "llama3.2:3b": {"latency": 0.7, "accuracy": 0.7},
                "llama3.1:8b": {"latency": 0.7, "accuracy": 0.7},
                "qwen2.5:14b": {"latency": 0.1, "accuracy": 0.1},
            },
        )
        router._warm_models = {"llama3.1:8b"}
        # 100 words: between the <=12 and >250 length shortcuts.
        prompt = " ".join(["word"] * 100)
        assert router._choose_initial_tier(_request(prompt)) == "L4"
