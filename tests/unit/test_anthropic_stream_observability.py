"""Anthropic stream observability + latency parity (issue #101)."""

from __future__ import annotations

import pytest

from daari.cache.exact import ExactCache
from daari.cache.semantic import SemanticCache
from daari.gateway.internal import InternalRequest, Message, RequestMeta
from daari.observability.metrics import Metrics
from daari.router.model_profile import ModelProfileStore
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
        stream=True,
        meta=RequestMeta(latency_budget_ms=latency_budget_ms),
    )


@pytest.fixture
def captured_events(monkeypatch):
    events: list[tuple[str, dict]] = []

    def capture(event: str, payload: dict) -> None:
        events.append((event, payload))

    monkeypatch.setattr("daari.gateway.request_log.log_gateway_event", capture)
    return events


def _mock_stream(monkeypatch, router, content="A confident answer.", fail_tiers=()):
    for attr in ("ollama_l3", "ollama_l4", "ollama_l5"):
        executor = getattr(router, attr)

        async def fake_stream(request, _tier=executor.tier):
            if _tier in fail_tiers:
                raise TimeoutError()
            yield {"message": {"role": "assistant", "content": content}, "done": False}
            yield {"message": {"role": "assistant", "content": ""}, "done": True}

        monkeypatch.setattr(executor, "stream", fake_stream)


@pytest.mark.asyncio
async def test_success_logs_anthropic_stream_done(tmp_path, monkeypatch, captured_events):
    router = _router(tmp_path)
    _mock_stream(monkeypatch, router)
    async for _ in router.stream_anthropic_events(_request("hello there")):
        pass
    done = [p for e, p in captured_events if e == "anthropic_stream_done"]
    assert len(done) == 1
    assert done[0]["tier"] == "L3"
    assert done[0]["completion_chars"] == len("A confident answer.")
    assert done[0]["latency_ms"] >= 0
    assert done[0]["empty"] is False


@pytest.mark.asyncio
async def test_failure_logs_exception_type(tmp_path, monkeypatch, captured_events):
    router = _router(tmp_path)
    # TimeoutError stringifies to "" — the type name must still identify it.
    _mock_stream(monkeypatch, router, fail_tiers=("L4",))
    long_prompt = "please explain this " + "word " * 300  # L4 first
    async for _ in router.stream_anthropic_events(_request(long_prompt)):
        pass
    failed = [p for e, p in captured_events if e == "anthropic_stream_attempt_failed"]
    assert failed and failed[0]["error_type"] == "TimeoutError"
    assert failed[0]["tier"] == "L4"
    done = [p for e, p in captured_events if e == "anthropic_stream_done"]
    assert done and done[0]["tier"] == "L3", "fallback success must be visible"


@pytest.mark.asyncio
async def test_latency_budget_steps_anthropic_chain_down(tmp_path, monkeypatch, captured_events):
    store = ModelProfileStore(tmp_path / "models.json")
    store.save(
        {
            "llama3.2:3b": {"latency_ms": 700.0},
            "llama3.1:8b": {"latency_ms": 2500.0},
        }
    )
    router = _router(tmp_path, model_profile_store=store)
    _mock_stream(monkeypatch, router)
    long_prompt = "please explain this " + "word " * 300  # heuristic picks L4
    async for _ in router.stream_anthropic_events(
        _request(long_prompt, latency_budget_ms=1000)
    ):
        pass
    done = [p for e, p in captured_events if e == "anthropic_stream_done"]
    assert done and done[0]["tier"] == "L3", "profiled 2500ms L4 must step down under a 1000ms budget"
