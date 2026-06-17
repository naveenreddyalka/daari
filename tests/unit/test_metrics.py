from __future__ import annotations

from daari.observability.metrics import Metrics, TierStats


class TestTierStats:
    def test_avg_latency_zero_when_empty(self):
        assert TierStats().avg_latency_ms == 0.0

    def test_avg_latency_computed(self):
        stats = TierStats(count=2, total_latency_ms=100)
        assert stats.avg_latency_ms == 50.0


class TestMetrics:
    def test_record_tier_counts(self):
        metrics = Metrics()
        metrics.record("L3", latency_ms=10)
        metrics.record("L0", cache_hit=True, latency_ms=1)
        snap = metrics.snapshot()
        assert snap["L3"]["count"] == 1
        assert snap["L0"]["cache_hits"] == 1

    def test_record_error(self):
        metrics = Metrics()
        metrics.record_error()
        assert metrics.errors == 1
