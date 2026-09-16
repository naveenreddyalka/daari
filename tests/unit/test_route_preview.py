"""Dry-run preview of the initial local tier (#538)."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from typer.testing import CliRunner

from daari.cache.exact import ExactCache
from daari.cache.semantic import SemanticCache
from daari.cli.app import app as cli_app
from daari.gateway.internal import InternalRequest, Message, RequestMeta
from daari.observability.metrics import Metrics
from daari.router.router import AppContext, OllamaExecutor, Router
from daari.server.app import create_app
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


def _request(text: str, **meta: object) -> InternalRequest:
    return InternalRequest(
        messages=[Message(role="user", content=text)],
        model="daari",
        meta=RequestMeta(**meta) if meta else RequestMeta(),
    )


def test_preview_short_prompt_is_l3(tmp_path):
    preview = _router(tmp_path).preview_initial_tier(_request("hi"))
    assert preview["tier"] == "L3"
    assert preview["reasons"]["heuristic"] == "L3"
    assert preview["reasons"]["ttft_preference"] is None


def test_preview_long_prompt_is_l4(tmp_path):
    text = " ".join(["word"] * 300)
    preview = _router(tmp_path).preview_initial_tier(_request(text))
    assert preview["tier"] == "L4"
    assert preview["reasons"]["heuristic"] == "L4"


def test_preview_ttft_preference_is_explained(tmp_path):
    metrics = Metrics()
    for _ in range(30):
        metrics.record_ttft("L3", ttft_ms=30)
        metrics.record_ttft("L4", ttft_ms=400)
    router = _router(
        tmp_path,
        metrics=metrics,
        ttft_aware=True,
        ttft_percentile=0.95,
        ttft_min_samples=20,
    )
    text = " ".join(["word"] * 300)
    preview = router.preview_initial_tier(_request(text))
    assert preview["reasons"]["heuristic"] == "L4"
    assert preview["reasons"]["ttft_preference"] == "L3"
    assert preview["tier"] == "L3"


@pytest.mark.asyncio
async def test_preview_http_endpoint(settings):
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/daari/route/preview",
            json={"messages": [{"role": "user", "content": "hi"}]},
        )
    assert response.status_code == 200
    body = response.json()
    assert body["tier"] in {"L3", "L4", "L5"}
    assert "heuristic" in body["reasons"]


def test_cli_route_preview(tmp_path, monkeypatch):
    router = _router(tmp_path)
    monkeypatch.setattr(
        "daari.cli.app._route_preview_router",
        lambda: router,
    )
    result = CliRunner().invoke(cli_app, ["route", "preview", "hi"])
    assert result.exit_code == 0
    assert '"tier": "L3"' in result.stdout
