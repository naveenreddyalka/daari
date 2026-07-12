"""Phase D1b: learn stats aggregation + tier recommendations (issue #54)."""

from __future__ import annotations

import yaml

from daari.config.settings import Settings
from daari.learning.feedback import FeedbackStore
from daari.learning.recommend import recommend_policies, recommendation_yaml


def _store(tmp_path) -> FeedbackStore:
    return FeedbackStore(str(tmp_path / "feedback.sqlite3"))


def _seed(store: FeedbackStore, *, category: str, tier: str, count: int,
          escalated: int = 0, rejects: int = 0, accepts: int = 0,
          confidence: float = 0.9, latency_ms: int = 100) -> None:
    for i in range(count):
        trace_id = f"{category}-{tier}-{i}"
        store.record_outcome(
            trace_id=trace_id, category=category, complexity="standard",
            tier=tier, confidence=confidence,
            escalated=i < escalated, latency_ms=latency_ms,
        )
        if i < rejects:
            store.record_signal(trace_id, "reject")
        elif i < rejects + accepts:
            store.record_signal(trace_id, "accept")


class TestStatsAggregation:
    def test_stats_groups_by_category_and_tier(self, tmp_path):
        store = _store(tmp_path)
        _seed(store, category="doc_qa", tier="L3", count=10, escalated=1, accepts=3)
        _seed(store, category="code_gen", tier="L4", count=5, escalated=4, rejects=2)

        stats = store.stats(days=7)

        doc_qa = stats["doc_qa"]["L3"]
        assert doc_qa["outcomes"] == 10
        assert doc_qa["escalated"] == 1
        assert doc_qa["escalation_rate"] == 0.1
        assert doc_qa["accepts"] == 3
        assert doc_qa["rejects"] == 0
        assert doc_qa["avg_confidence"] == 0.9
        assert doc_qa["avg_latency_ms"] == 100

        code_gen = stats["code_gen"]["L4"]
        assert code_gen["outcomes"] == 5
        assert code_gen["escalation_rate"] == 0.8
        assert code_gen["rejects"] == 2

    def test_stats_empty_store(self, tmp_path):
        assert _store(tmp_path).stats(days=7) == {}

    def test_disabled_store_stats_empty(self, tmp_path):
        store = FeedbackStore(str(tmp_path / "f.sqlite3"), enabled=False)
        assert store.stats(days=7) == {}


class TestRecommendations:
    def test_reliable_category_recommends_cheapest_good_tier(self, tmp_path):
        store = _store(tmp_path)
        # L3 serves doc_qa well: 5% escalation, no rejects.
        _seed(store, category="doc_qa", tier="L3", count=40, escalated=2, accepts=10)

        recs = recommend_policies(store.stats(days=7), min_samples=20)

        assert recs["doc_qa"]["tier"] == "L3"
        assert recs["doc_qa"]["evidence"]["outcomes"] == 40

    def test_weak_tier_skipped_for_next_tier_up(self, tmp_path):
        store = _store(tmp_path)
        # L3 escalates 50% of code_gen; L4 holds at 5%.
        _seed(store, category="code_gen", tier="L3", count=30, escalated=15)
        _seed(store, category="code_gen", tier="L4", count=30, escalated=1)

        recs = recommend_policies(store.stats(days=7), min_samples=20)

        assert recs["code_gen"]["tier"] == "L4"

    def test_high_reject_rate_disqualifies_tier(self, tmp_path):
        store = _store(tmp_path)
        # Low escalation but 20% explicit rejects — users say it's wrong.
        _seed(store, category="chat", tier="L3", count=30, escalated=0, rejects=6)
        _seed(store, category="chat", tier="L4", count=30, escalated=1, accepts=5)

        recs = recommend_policies(store.stats(days=7), min_samples=20)

        assert recs["chat"]["tier"] == "L4"

    def test_below_min_samples_omitted(self, tmp_path):
        store = _store(tmp_path)
        _seed(store, category="doc_qa", tier="L3", count=5)

        recs = recommend_policies(store.stats(days=7), min_samples=20)

        assert recs == {}

    def test_no_qualifying_tier_omitted(self, tmp_path):
        store = _store(tmp_path)
        # Every observed tier is bad; never guess an unobserved one.
        _seed(store, category="code_gen", tier="L3", count=30, escalated=20)

        recs = recommend_policies(store.stats(days=7), min_samples=20)

        assert recs == {}


class TestYamlRoundTrip:
    def test_yaml_block_validates_as_settings(self, tmp_path):
        store = _store(tmp_path)
        _seed(store, category="doc_qa", tier="L3", count=40, escalated=1)
        recs = recommend_policies(store.stats(days=7), min_samples=20)

        block = recommendation_yaml(recs)

        parsed = yaml.safe_load(block)
        settings = Settings.model_validate(
            {"routing": {"category_policies": parsed["routing"]["category_policies"]}}
        )
        assert settings.routing.category_policies["doc_qa"].tier == "L3"

    def test_empty_recommendations_yaml_is_comment_only(self):
        block = recommendation_yaml({})
        assert "no recommendations" in block
        assert yaml.safe_load(block) is None


class TestCli:
    def test_learn_stats_and_recommend_cli(self, tmp_path, monkeypatch):
        from typer.testing import CliRunner

        from daari.cli.app import app as cli_app
        from daari.config.settings import Settings

        settings = Settings.model_validate(
            {"learning": {"path": str(tmp_path / "feedback.sqlite3")}}
        )
        monkeypatch.setattr("daari.cli.app.get_settings", lambda: settings)

        store = FeedbackStore(str(tmp_path / "feedback.sqlite3"))
        _seed(store, category="doc_qa", tier="L3", count=25, escalated=1, accepts=5)

        runner = CliRunner()
        stats_result = runner.invoke(cli_app, ["learn", "stats"])
        assert stats_result.exit_code == 0
        assert "doc_qa" in stats_result.output
        assert "25" in stats_result.output

        rec_result = runner.invoke(cli_app, ["learn", "recommend", "--min-samples", "20"])
        assert rec_result.exit_code == 0
        assert "category_policies" in rec_result.output
        assert "tier: L3" in rec_result.output

    def test_learn_stats_empty_hint(self, tmp_path, monkeypatch):
        from typer.testing import CliRunner

        from daari.cli.app import app as cli_app
        from daari.config.settings import Settings

        settings = Settings.model_validate(
            {"learning": {"path": str(tmp_path / "feedback.sqlite3")}}
        )
        monkeypatch.setattr("daari.cli.app.get_settings", lambda: settings)

        runner = CliRunner()
        result = runner.invoke(cli_app, ["learn", "stats"])
        assert result.exit_code == 0
        assert "No outcomes recorded yet" in result.output
