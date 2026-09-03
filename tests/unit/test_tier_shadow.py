"""Shadow evals for tier decisions (issue #318).

A sampled request served by a local tier is re-run in the background at a
comparison tier; answer similarity is recorded per category. Never blocks or
changes the served response, never touches cache / ledger / outcome capture.
"""

from __future__ import annotations

import asyncio

import pytest
from pydantic import ValidationError
from typer.testing import CliRunner

from daari.cache.exact import ExactCache
from daari.cache.semantic import SemanticCache
from daari.config.settings import Settings
from daari.gateway.internal import DaariMeta, InternalRequest, InternalResponse, Message
from daari.learning.feedback import FeedbackStore
from daari.observability.metrics import Metrics
from daari.observability.prometheus import render_prometheus
from daari.observability.trace import TraceStore
from daari.router.router import OllamaExecutor, Router


class WordEmbedder:
    """Identical answers embed identically; anything else is orthogonal."""

    async def embed(self, text: str) -> list[float] | None:
        if "alpha" in text:
            return [1.0, 0.0]
        return [0.0, 1.0]


def _request(text: str = "what is a mutex?") -> InternalRequest:
    return InternalRequest(messages=[Message(role="user", content=text)], model="daari")


def _response(content: str, tier: str = "L3") -> InternalResponse:
    return InternalResponse(
        content=content,
        model="m",
        daari_meta=DaariMeta(tier=tier, executor="ollama", provider_id="ollama", latency_ms=1),
    )


def _executor(model: str, tier: str, content: str) -> OllamaExecutor:
    executor = OllamaExecutor(base_url="http://test", default_model=model, tier=tier)
    calls: list[InternalRequest] = []

    async def fake_execute(request: InternalRequest) -> InternalResponse:
        calls.append(request)
        return _response(content, tier)

    executor.execute = fake_execute  # type: ignore[method-assign]
    executor.calls = calls  # type: ignore[attr-defined]
    return executor


def _router(tmp_path, *, feedback=None, l5_content="beta answer", **kwargs) -> Router:
    l3 = _executor("small", "L3", "alpha answer")
    l5 = _executor("large", "L5", l5_content)
    return Router(
        cache=ExactCache(str(tmp_path / "l0"), enabled=True),
        semantic_cache=SemanticCache(str(tmp_path / "l1"), WordEmbedder(), enabled=False),
        ollama=l3,
        ollama_l4=l3,
        ollama_l5=l5,
        metrics=Metrics(),
        frontier=None,
        frontier_enabled=False,
        trace_store=TraceStore(tmp_path / "traces.sqlite3"),
        feedback_store=feedback,
        l1_shadow_sample_rate=0.0,
        **kwargs,
    )


class TestSettings:
    def test_defaults_are_off(self):
        routing = Settings().routing
        assert routing.shadow_sample_rate == 0.0
        assert routing.shadow_compare_tier == ""
        assert routing.shadow_daily_usd == 0.0

    def test_compare_tier_must_be_a_tier(self):
        with pytest.raises(ValidationError):
            Settings.model_validate({"routing": {"shadow_compare_tier": "L9"}})
        assert (
            Settings.model_validate(
                {"routing": {"shadow_compare_tier": "l5"}}
            ).routing.shadow_compare_tier
            == "L5"
        )


class TestFeedbackStore:
    def test_tier_shadow_stats_groups_by_category(self, tmp_path):
        store = FeedbackStore(str(tmp_path / "f.sqlite3"))
        store.record_tier_shadow(
            category="doc_qa", served_tier="L3", compare_tier="L5", similarity=0.95, agreed=True
        )
        store.record_tier_shadow(
            category="doc_qa", served_tier="L3", compare_tier="L5", similarity=0.20, agreed=False
        )
        store.record_tier_shadow(
            category="code_gen", served_tier="L4", compare_tier="L5", similarity=0.90, agreed=True
        )
        stats = store.tier_shadow_stats(days=7)
        assert stats["doc_qa"] == {
            "samples": 2,
            "agreements": 1,
            "agree_rate": 0.5,
            "divergence_rate": 0.5,
            "avg_answer_similarity": 0.575,
            "compare_tiers": {"L5": 2},
            "served_tiers": {"L3": 2},
        }
        assert stats["code_gen"]["agree_rate"] == 1.0

    def test_disabled_store_is_silent(self, tmp_path):
        store = FeedbackStore(str(tmp_path / "f.sqlite3"), enabled=False)
        store.record_tier_shadow(
            category="doc_qa", served_tier="L3", compare_tier="L5", similarity=0.9, agreed=True
        )
        assert store.tier_shadow_stats(days=7) == {}


class TestRouterSampling:
    @pytest.mark.asyncio
    async def test_sampled_local_response_is_compared_against_top_local_tier(self, tmp_path):
        feedback = FeedbackStore(str(tmp_path / "f.sqlite3"))
        router = _router(tmp_path, feedback=feedback, tier_shadow_sample_rate=1.0)

        response = await router.route(_request())
        assert response.daari_meta.tier == "L3"
        assert response.content == "alpha answer", "served answer is never altered"
        await asyncio.gather(*router._shadow_tasks)

        stats = feedback.tier_shadow_stats(days=1)
        assert stats["doc_qa"]["samples"] == 1
        assert stats["doc_qa"]["agreements"] == 0
        assert stats["doc_qa"]["compare_tiers"] == {"L5": 1}
        assert len(router.ollama_l5.calls) == 1
        assert router.ollama_l5.calls[0].model == "large"
        assert router.metrics.snapshot(include_histograms=True)["tier_shadow"] == {"disagree": 1}

    @pytest.mark.asyncio
    async def test_agreeing_answers_count_as_agreement(self, tmp_path):
        feedback = FeedbackStore(str(tmp_path / "f.sqlite3"))
        router = _router(
            tmp_path, feedback=feedback, l5_content="alpha answer too", tier_shadow_sample_rate=1.0
        )
        await router.route(_request())
        await asyncio.gather(*router._shadow_tasks)
        assert feedback.tier_shadow_stats(days=1)["doc_qa"]["agree_rate"] == 1.0
        assert router.metrics.snapshot(include_histograms=True)["tier_shadow"] == {"agree": 1}

    @pytest.mark.asyncio
    async def test_shadow_run_leaves_cache_ledger_and_outcomes_alone(self, tmp_path):
        feedback = FeedbackStore(str(tmp_path / "f.sqlite3"))

        class Ledger:
            rows: list[dict] = []

            def record(self, **row):
                self.rows.append(row)

        ledger = Ledger()
        router = _router(
            tmp_path, feedback=feedback, tier_shadow_sample_rate=1.0, usage_ledger=ledger
        )
        await router.route(_request())
        await asyncio.gather(*router._shadow_tasks)

        assert [row["tier"] for row in ledger.rows] == ["L3"]
        outcomes = feedback.stats(days=1)
        assert set(outcomes["doc_qa"]) == {"L3"}
        assert outcomes["doc_qa"]["L3"]["outcomes"] == 1
        # The L0 cache holds exactly the served answer; the shadow answer was never written.
        again = await router.route(_request())
        assert again.daari_meta.tier == "L0"
        assert again.content == "alpha answer"

    @pytest.mark.asyncio
    async def test_zero_rate_never_samples(self, tmp_path):
        feedback = FeedbackStore(str(tmp_path / "f.sqlite3"))
        router = _router(tmp_path, feedback=feedback, tier_shadow_sample_rate=0.0)
        await router.route(_request())
        await asyncio.gather(*router._shadow_tasks)
        assert feedback.tier_shadow_stats(days=1) == {}
        assert router.ollama_l5.calls == []

    @pytest.mark.asyncio
    async def test_no_distinct_higher_tier_means_no_shadow(self, tmp_path):
        feedback = FeedbackStore(str(tmp_path / "f.sqlite3"))
        l3 = _executor("small", "L3", "alpha answer")
        router = Router(
            cache=ExactCache(str(tmp_path / "l0"), enabled=False),
            semantic_cache=SemanticCache(str(tmp_path / "l1"), WordEmbedder(), enabled=False),
            ollama=l3,
            metrics=Metrics(),
            frontier=None,
            frontier_enabled=False,
            trace_store=TraceStore(tmp_path / "traces.sqlite3"),
            feedback_store=feedback,
            l1_shadow_sample_rate=0.0,
            tier_shadow_sample_rate=1.0,
        )
        await router.route(_request())
        await asyncio.gather(*router._shadow_tasks)
        assert feedback.tier_shadow_stats(days=1) == {}
        assert len(l3.calls) == 1

    @pytest.mark.asyncio
    async def test_cache_hits_are_not_sampled(self, tmp_path):
        feedback = FeedbackStore(str(tmp_path / "f.sqlite3"))
        router = _router(tmp_path, feedback=feedback, tier_shadow_sample_rate=1.0)
        await router.route(_request())
        await asyncio.gather(*router._shadow_tasks)
        hit = await router.route(_request())
        assert hit.daari_meta.tier == "L0"
        await asyncio.gather(*router._shadow_tasks)
        assert feedback.tier_shadow_stats(days=1)["doc_qa"]["samples"] == 1

    @pytest.mark.asyncio
    async def test_shadow_failure_never_breaks_serving(self, tmp_path):
        feedback = FeedbackStore(str(tmp_path / "f.sqlite3"))
        router = _router(tmp_path, feedback=feedback, tier_shadow_sample_rate=1.0)

        async def boom(request):
            raise RuntimeError("model down")

        router.ollama_l5.execute = boom  # type: ignore[method-assign]
        response = await router.route(_request())
        assert response.content == "alpha answer"
        await asyncio.gather(*router._shadow_tasks)
        assert feedback.tier_shadow_stats(days=1) == {}


class _Frontier:
    api_key = "sk"

    def __init__(self) -> None:
        self.calls = 0

    async def execute(self, request, **_kwargs):
        self.calls += 1
        return InternalResponse(
            content="beta from the frontier " * 20,
            model="gpt",
            daari_meta=DaariMeta(
                tier="L6", executor="frontier", provider_id="openai", latency_ms=1
            ),
        )


class TestFrontierComparison:
    @pytest.mark.asyncio
    async def test_l6_requires_a_shadow_budget(self, tmp_path):
        feedback = FeedbackStore(str(tmp_path / "f.sqlite3"))
        frontier = _Frontier()
        router = _router(
            tmp_path,
            feedback=feedback,
            tier_shadow_sample_rate=1.0,
            tier_shadow_compare_tier="L6",
            tier_shadow_daily_usd=0.0,
        )
        router.frontier = frontier
        router.frontier_enabled = True
        await router.route(_request())
        await asyncio.gather(*router._shadow_tasks)
        assert frontier.calls == 0
        assert feedback.tier_shadow_stats(days=1) == {}

    @pytest.mark.asyncio
    async def test_l6_shadow_spend_is_capped(self, tmp_path):
        feedback = FeedbackStore(str(tmp_path / "f.sqlite3"))
        frontier = _Frontier()
        router = _router(
            tmp_path,
            feedback=feedback,
            tier_shadow_sample_rate=1.0,
            tier_shadow_compare_tier="L6",
            tier_shadow_daily_usd=0.0001,
            frontier_price_per_1k_tokens=1.0,
        )
        router.frontier = frontier
        router.frontier_enabled = True
        await router.route(_request("first question"))
        await asyncio.gather(*router._shadow_tasks)
        assert frontier.calls == 1
        assert router.tier_shadow_spend_usd > 0
        await router.route(_request("second question"))
        await asyncio.gather(*router._shadow_tasks)
        assert frontier.calls == 1, "cap reached after the first shadow run"
        (row,) = feedback.tier_shadow_stats(days=1).values()
        assert row["samples"] == 1
        assert row["compare_tiers"] == {"L6": 1}


class TestReporting:
    def test_metrics_and_prometheus(self):
        metrics = Metrics()
        metrics.record_tier_shadow(agreed=True)
        metrics.record_tier_shadow(agreed=True)
        metrics.record_tier_shadow(agreed=False)
        snap = metrics.snapshot(include_histograms=True)
        assert snap["tier_shadow"] == {"agree": 2, "disagree": 1}
        text = render_prometheus(metrics)
        assert 'daari_tier_shadow_samples_total{agreed="true"} 2' in text
        assert 'daari_tier_shadow_samples_total{agreed="false"} 1' in text

    def test_learn_stats_prints_tier_divergence(self, tmp_path, monkeypatch):
        from daari.cli import app as cli_app

        store = FeedbackStore(str(tmp_path / "f.sqlite3"))
        store.record_outcome(
            trace_id="t1",
            category="doc_qa",
            complexity="standard",
            tier="L3",
            confidence=0.9,
            escalated=False,
            latency_ms=10,
        )
        store.record_tier_shadow(
            category="doc_qa", served_tier="L3", compare_tier="L5", similarity=0.3, agreed=False
        )
        store.record_tier_shadow(
            category="doc_qa", served_tier="L3", compare_tier="L5", similarity=0.9, agreed=True
        )
        monkeypatch.setattr(cli_app, "_feedback_store", lambda: store)
        result = CliRunner().invoke(cli_app.app, ["learn", "stats"])
        assert result.exit_code == 0, result.output
        assert "Tier divergence" in result.output
        assert "doc_qa" in result.output
        assert "50.0%" in result.output
        assert "L5" in result.output
