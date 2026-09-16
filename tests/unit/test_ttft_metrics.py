"""Stream TTFT histogram wiring (#508)."""

from __future__ import annotations

import asyncio

import pytest

from daari.cache.exact import ExactCache
from daari.cache.semantic import SemanticCache
from daari.gateway.internal import InternalRequest, Message
from daari.observability.metrics import Metrics
from daari.observability.prometheus import render_prometheus
from daari.router.router import OllamaExecutor, Router
from tests.conftest import NoopEmbedder


@pytest.mark.asyncio
async def test_stream_records_ttft_histogram(tmp_path):
    metrics = Metrics()
    release = asyncio.Event()

    async def fake_stream(request: InternalRequest):
        await release.wait()
        yield {"message": {"content": "hello"}, "done": False}
        yield {"message": {"content": ""}, "done": True}

    ollama = OllamaExecutor(base_url="http://test", default_model="llama3.2:3b")
    ollama.stream = fake_stream  # type: ignore[method-assign]
    router = Router(
        cache=ExactCache(str(tmp_path / "c"), enabled=True),
        semantic_cache=SemanticCache(
            str(tmp_path / "l1"), NoopEmbedder(), enabled=False
        ),
        ollama=ollama,
        metrics=metrics,
        frontier_enabled=False,
    )
    request = InternalRequest(
        messages=[Message(role="user", content="ttft please")],
        model="llama3.2:3b",
    )
    release.set()
    async for _ in router.stream_openai_chunks(request):
        pass

    snap = metrics.snapshot(include_histograms=True)
    assert "L3" in snap["ttft"]
    assert snap["ttft"]["L3"]["count"] == 1
    text = render_prometheus(metrics)
    assert 'daari_ttft_ms_count{tier="L3"} 1' in text
