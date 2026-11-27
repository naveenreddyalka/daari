"""Prometheus and stats counters for settled finish_reason / stop_reason (#2338)."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from daari.cache.exact import ExactCache
from daari.cache.semantic import SemanticCache
from daari.gateway.internal import DaariMeta, InternalRequest, InternalResponse, Message
from daari.observability.metrics import Metrics
from daari.observability.prometheus import render_prometheus
from daari.router.router import AppContext, OllamaExecutor, Router
from daari.server.app import create_app
from tests.conftest import NoopEmbedder

_KNOWN = ("stop", "tool_calls", "length", "pause_turn", "refusal", "content_filter")


def test_record_finish_reason_buckets_honest_aliases_and_unknown():
    metrics = Metrics()
    for reason in _KNOWN:
        metrics.record_finish_reason(reason)
    # Anthropic stop_reason aliases collapse onto the OpenAI-shaped label.
    metrics.record_finish_reason("max_tokens")
    metrics.record_finish_reason("end_turn")
    metrics.record_finish_reason("tool_use")
    metrics.record_finish_reason("stop_sequence")
    metrics.record_finish_reason("  Refusal ")
    metrics.record_finish_reason("CONTENT_FILTER")
    # Blank is the wire default (stop). Unknown tokens stay bounded as other.
    metrics.record_finish_reason("")
    metrics.record_finish_reason(None)
    metrics.record_finish_reason("banana")
    metrics.record_finish_reason("incomplete")

    snap = metrics.snapshot(include_histograms=True)
    assert snap["finish_reason"] == {
        "stop": 5,  # stop, end_turn, stop_sequence, "", None
        "tool_calls": 2,  # tool_calls, tool_use
        "length": 2,  # length, max_tokens
        "pause_turn": 1,
        "refusal": 2,
        "content_filter": 2,
        "other": 2,  # banana, incomplete (Responses status is a separate series)
    }


def test_prometheus_emits_finish_reason_zero_then_labels():
    text0 = render_prometheus(Metrics())
    assert "# HELP daari_finish_reason_total" in text0
    assert "pause_turn" in text0
    assert "refusal" in text0
    assert "# TYPE daari_finish_reason_total counter" in text0
    assert "daari_finish_reason_total 0" in text0
    assert "daari_finish_reason_total{" not in text0

    metrics = Metrics()
    metrics.record_finish_reason("length")
    metrics.record_finish_reason("max_tokens")
    metrics.record_finish_reason("pause_turn")
    metrics.record_finish_reason("not-a-reason")
    text = render_prometheus(metrics)
    assert 'daari_finish_reason_total{reason="length"} 2' in text
    assert 'daari_finish_reason_total{reason="pause_turn"} 1' in text
    assert 'daari_finish_reason_total{reason="other"} 1' in text
    assert "daari_finish_reason_total 0" not in text


@pytest.mark.asyncio
async def test_stats_exposes_finish_reason_map(settings):
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    app.state.ctx.metrics.record_finish_reason("refusal")
    app.state.ctx.metrics.record_finish_reason("tool_use")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/v1/daari/stats")

    assert response.status_code == 200
    assert response.json()["finish_reason"] == {"refusal": 1, "tool_calls": 1}


class _Executor(OllamaExecutor):
    def __init__(self, *, text: str = "a complete local answer", done_reason: str = "stop") -> None:
        super().__init__(base_url="http://test", default_model="llama3.2:3b")
        self.text = text
        self.done_reason = done_reason

    async def execute(self, request: InternalRequest) -> InternalResponse:  # type: ignore[override]
        return InternalResponse(
            content=self.text,
            model="llama3.2:3b",
            finish_reason=self.done_reason,
            daari_meta=DaariMeta(tier="L3", executor="ollama", provider_id="ollama:l3"),
        )

    async def stream(self, request, **kwargs):  # type: ignore[override]
        yield {"message": {"content": self.text}}
        yield {"message": {"content": ""}, "done": True, "done_reason": self.done_reason}


def _request(text: str = "explain exact caches") -> InternalRequest:
    return InternalRequest(messages=[Message(role="user", content=text)], model="daari")


def _router(tmp_path, executor: _Executor) -> Router:
    metrics = Metrics()
    return Router(
        cache=ExactCache(str(tmp_path / "l0"), enabled=False),
        semantic_cache=SemanticCache(str(tmp_path / "l1"), NoopEmbedder(), enabled=False),
        ollama=executor,
        ollama_l3=executor,
        ollama_l4=executor,
        ollama_l5=executor,
        metrics=metrics,
        frontier_enabled=False,
    )


def _counts(router: Router) -> dict[str, int]:
    return dict(router.metrics.snapshot(include_histograms=True)["finish_reason"])


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("done_reason", "label"),
    [
        ("stop", "stop"),
        ("tool_calls", "tool_calls"),
        ("length", "length"),
        ("max_tokens", "length"),
        ("pause_turn", "pause_turn"),
        ("refusal", "refusal"),
        ("content_filter", "content_filter"),
        ("end_turn", "stop"),
        ("tool_use", "tool_calls"),
        ("banana", "other"),
    ],
)
async def test_route_counts_settled_finish_reason(tmp_path, done_reason, label):
    """Chat, messages, and responses non-stream all settle through route()."""
    router = _router(tmp_path, _Executor(done_reason=done_reason))
    response = await router.route(_request(f"non-stream {done_reason}"))
    assert response.finish_reason == done_reason
    assert _counts(router) == {label: 1}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("done_reason", "label"),
    [
        ("stop", "stop"),
        ("length", "length"),
        ("max_tokens", "length"),
        ("pause_turn", "pause_turn"),
        ("refusal", "refusal"),
        ("tool_use", "tool_calls"),
    ],
)
async def test_chat_and_responses_stream_counts_terminal_finish_reason(
    tmp_path, done_reason, label
):
    """Chat and Responses streams share stream_openai_chunks."""
    router = _router(tmp_path, _Executor(done_reason=done_reason))
    chunks = [
        chunk async for chunk in router.stream_openai_chunks(_request(f"stream {done_reason}"))
    ]
    assert chunks
    assert _counts(router) == {label: 1}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("done_reason", "label"),
    [
        ("stop", "stop"),
        ("length", "length"),
        ("pause_turn", "pause_turn"),
        ("refusal", "refusal"),
        ("tool_use", "tool_calls"),
    ],
)
async def test_messages_stream_counts_terminal_stop_reason(tmp_path, done_reason, label):
    router = _router(tmp_path, _Executor(done_reason=done_reason))
    chunks = [
        chunk async for chunk in router.stream_anthropic_events(_request(f"messages {done_reason}"))
    ]
    assert chunks
    assert _counts(router) == {label: 1}


@pytest.mark.asyncio
async def test_aborted_stream_does_not_count_a_finish_reason(tmp_path):
    router = _router(tmp_path, _Executor(text="partial", done_reason="abort"))
    chunks = [chunk async for chunk in router.stream_openai_chunks(_request("abort me"))]
    assert any("stream_incomplete" in chunk for chunk in chunks)
    assert _counts(router) == {}
