"""Opt-in TTFT-aware local tier preference (#529)."""

from __future__ import annotations

from daari.cache.exact import ExactCache
from daari.cache.semantic import SemanticCache
from daari.config.settings import Settings
from daari.gateway.internal import InternalRequest, Message
from daari.observability.metrics import Metrics, histogram_percentile_ms
from daari.router.router import OllamaExecutor, Router
from tests.conftest import NoopEmbedder


def _router(tmp_path, *, metrics: Metrics | None = None, **kwargs) -> Router:
    return Router(
        cache=ExactCache(str(tmp_path / "l0"), enabled=False),
        semantic_cache=SemanticCache(
            str(tmp_path / "l1"), NoopEmbedder(), enabled=False
        ),
        ollama=OllamaExecutor(base_url="http://test", default_model="llama3.2:3b", tier="L3"),
        ollama_l4=OllamaExecutor(base_url="http://test", default_model="llama3.1:8b", tier="L4"),
        ollama_l5=OllamaExecutor(base_url="http://test", default_model="qwen2.5:14b", tier="L5"),
        metrics=metrics or Metrics(),
        frontier=None,
        frontier_enabled=False,
        **kwargs,
    )


def _request(text: str) -> InternalRequest:
    return InternalRequest(messages=[Message(role="user", content=text)], model="daari")


def _seed_ttft(metrics: Metrics, tier: str, values_ms: list[int]) -> None:
    for value in values_ms:
        metrics.record_ttft(tier, ttft_ms=value)


def test_histogram_percentile_from_buckets():
    # 20 samples all in the 50ms bucket → p95 ≈ 50.
    buckets = {50.0: 20}
    assert histogram_percentile_ms(buckets, count=20, percentile=0.95) == 50.0
    assert histogram_percentile_ms({}, count=0, percentile=0.95) is None


def test_settings_ttft_aware_defaults_off():
    settings = Settings()
    assert settings.routing.ttft_aware is False
    assert settings.routing.ttft_percentile == 0.95
    assert settings.routing.ttft_min_samples == 20


def test_default_off_preserves_heuristic_tier(tmp_path):
    """~300 words → L4; TTFT stats ignored when flag is off."""
    metrics = Metrics()
    _seed_ttft(metrics, "L3", [20] * 30)
    _seed_ttft(metrics, "L4", [400] * 30)
    router = _router(tmp_path, metrics=metrics, ttft_aware=False)
    text = " ".join(["word"] * 300)
    assert router._choose_initial_tier(_request(text)) == "L4"


def test_ttft_aware_prefers_faster_local_tier(tmp_path):
    """Heuristic L4; L3 has better recent p95 TTFT → prefer L3."""
    metrics = Metrics()
    _seed_ttft(metrics, "L3", [30] * 30)
    _seed_ttft(metrics, "L4", [400] * 30)
    router = _router(
        tmp_path,
        metrics=metrics,
        ttft_aware=True,
        ttft_percentile=0.95,
        ttft_min_samples=20,
    )
    text = " ".join(["word"] * 300)
    assert router._choose_initial_tier(_request(text)) == "L3"


def test_ttft_aware_skips_when_under_min_samples(tmp_path):
    metrics = Metrics()
    _seed_ttft(metrics, "L3", [30] * 5)
    _seed_ttft(metrics, "L4", [400] * 5)
    router = _router(
        tmp_path,
        metrics=metrics,
        ttft_aware=True,
        ttft_min_samples=20,
    )
    text = " ".join(["word"] * 300)
    assert router._choose_initial_tier(_request(text)) == "L4"


def test_ttft_preference_increments_prometheus_counter(tmp_path):
    """Preference rewrite bumps daari_ttft_preference_total{from,to}; no-op does not (#539)."""
    from daari.observability.prometheus import render_prometheus

    metrics = Metrics()
    _seed_ttft(metrics, "L3", [30] * 30)
    _seed_ttft(metrics, "L4", [400] * 30)
    router = _router(
        tmp_path,
        metrics=metrics,
        ttft_aware=True,
        ttft_percentile=0.95,
        ttft_min_samples=20,
    )
    text = " ".join(["word"] * 300)
    assert router._choose_initial_tier(_request(text)) == "L3"
    text_out = render_prometheus(metrics)
    assert "# TYPE daari_ttft_preference_total counter" in text_out
    assert 'daari_ttft_preference_total{from="L4",to="L3"} 1' in text_out

    # Flag off: heuristic L4, counter unchanged.
    off = Metrics()
    _seed_ttft(off, "L3", [30] * 30)
    _seed_ttft(off, "L4", [400] * 30)
    router_off = _router(tmp_path, metrics=off, ttft_aware=False)
    assert router_off._choose_initial_tier(_request(text)) == "L4"
    assert "daari_ttft_preference_total" not in render_prometheus(off)

    # Aware but no faster candidate (same tier wins): still no increment.
    noop = Metrics()
    _seed_ttft(noop, "L4", [30] * 30)
    router_noop = _router(
        tmp_path,
        metrics=noop,
        ttft_aware=True,
        ttft_min_samples=20,
    )
    assert router_noop._choose_initial_tier(_request(text)) == "L4"
    assert "daari_ttft_preference_total" not in render_prometheus(noop)
