"""Prometheus counter for cache-write tokens by TTL class (#1872)."""

from __future__ import annotations

from daari.observability.metrics import Metrics, cache_write_ttl_label
from daari.observability.prometheus import render_prometheus


def test_cache_write_ttl_label_bounds() -> None:
    assert cache_write_ttl_label("30m") == "30m"
    assert cache_write_ttl_label("12h") == "12h"
    assert cache_write_ttl_label("1h") == "1h"
    assert cache_write_ttl_label(None) == "unset"
    assert cache_write_ttl_label("") == "unset"
    assert cache_write_ttl_label("5m") == "unset"
    assert cache_write_ttl_label("weird") == "unset"


def test_cache_write_tokens_prometheus_by_ttl() -> None:
    metrics = Metrics()
    metrics.record_cache_write(tokens=1000, ttl="30m")
    metrics.record_cache_write(tokens=500, ttl="12h")
    metrics.record_cache_write(tokens=200, ttl=None)
    metrics.record_cache_write(tokens=0, ttl="30m")  # no-op
    text = render_prometheus(metrics)
    assert "# TYPE daari_cache_write_tokens_total counter" in text
    assert 'daari_cache_write_tokens_total{ttl="30m"} 1000' in text
    assert 'daari_cache_write_tokens_total{ttl="12h"} 500' in text
    assert 'daari_cache_write_tokens_total{ttl="unset"} 200' in text


def test_cache_write_tokens_prometheus_zero_when_empty() -> None:
    text = render_prometheus(Metrics())
    assert "daari_cache_write_tokens_total 0" in text
