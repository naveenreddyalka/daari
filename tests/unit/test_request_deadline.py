"""Request-scoped deadline across the escalation chain (#771)."""

from __future__ import annotations

import asyncio

import pytest
from httpx import ASGITransport, AsyncClient

from daari.cache.exact import ExactCache
from daari.cache.semantic import SemanticCache
from daari.config.settings import Settings
from daari.gateway.internal import DaariMeta, InternalRequest, InternalResponse, Message
from daari.observability.metrics import Metrics
from daari.observability.prometheus import render_prometheus
from daari.router.deadline import (
    RequestDeadlineExceeded,
    aiter_with_ttft_deadline,
    bind_request_deadline,
    nonstream_timeout,
    parse_deadline_ms,
    resolve_deadline_seconds,
)
from daari.router.router import AppContext, OllamaExecutor, Router
from daari.server.app import create_app
from tests.conftest import NoopEmbedder


def test_setting_defaults_to_absent():
    assert Settings().upstream.request_deadline_seconds is None


def test_header_wins_over_setting():
    assert resolve_deadline_seconds(0, 30.0) == 0.0
    assert resolve_deadline_seconds(1500, 30.0) == 1.5
    assert resolve_deadline_seconds(None, 30.0) == 30.0
    assert resolve_deadline_seconds(None, None) is None
    assert resolve_deadline_seconds(None, 0) is None
    assert parse_deadline_ms("nope") is None
    assert parse_deadline_ms("250") == 250


def test_effective_timeout_is_min_of_tier_and_remaining():
    clock = {"t": 10.0}

    def now() -> float:
        return clock["t"]

    with bind_request_deadline(5.0, monotonic=now):
        assert nonstream_timeout(120.0, "L3") == 5.0
        clock["t"] = 12.0
        assert nonstream_timeout(90.0, "L4") == 3.0
        clock["t"] = 15.0
        with pytest.raises(RequestDeadlineExceeded) as caught:
            nonstream_timeout(90.0, "L6")
    assert caught.value.deadline_seconds == 5.0
    assert "L6" not in caught.value.tiers
    assert caught.value.tiers == ["L3", "L4"]


def test_unbound_timeout_is_the_configured_value():
    assert nonstream_timeout(120.0, "L3") == 120.0


@pytest.mark.asyncio
async def test_stream_deadline_is_ttft_only():
    async def chunks():
        yield "first"
        await asyncio.sleep(0.05)
        yield "second"

    with bind_request_deadline(0.02):
        seen = [item async for item in aiter_with_ttft_deadline(chunks())]
    assert seen == ["first", "second"]


@pytest.mark.asyncio
async def test_stream_timeout_before_first_token_raises():
    started: list[str] = []

    async def slow():
        started.append("open")
        await asyncio.sleep(0.4)
        yield "late"
        started.append("late")

    with bind_request_deadline(0.05):
        with pytest.raises(RequestDeadlineExceeded, match="deadline"):
            async for _ in aiter_with_ttft_deadline(slow()):
                started.append("yielded")
    assert started == ["open"]


def _router(tmp_path, *, deadline: float | None, calls: list[str], frontier) -> Router:
    def make_executor(tier: str) -> OllamaExecutor:
        executor = OllamaExecutor(
            base_url="http://test", default_model=f"model-{tier.lower()}", tier=tier
        )

        async def fake_execute(request: InternalRequest, _tier: str = tier) -> InternalResponse:
            calls.append(_tier)
            return InternalResponse(
                content="no",
                model=f"model-{_tier.lower()}",
                daari_meta=DaariMeta(tier=_tier, executor="ollama", latency_ms=1),
            )

        executor.execute = fake_execute  # type: ignore[method-assign]
        return executor

    return Router(
        cache=ExactCache(str(tmp_path / "l0"), enabled=True),
        semantic_cache=SemanticCache(
            path=str(tmp_path / "l1"), embedder=NoopEmbedder(), enabled=False
        ),
        ollama_l3=make_executor("L3"),
        ollama_l4=make_executor("L4"),
        ollama_l5=make_executor("L5"),
        metrics=Metrics(),
        frontier=frontier,
        frontier_enabled=True,
        request_deadline_seconds=deadline,
    )


class _Frontier:
    api_key = "sk-test"

    def __init__(self) -> None:
        self.calls = 0

    async def execute(self, *args, **kwargs):
        self.calls += 1
        raise AssertionError("frontier must not be called")


@pytest.mark.asyncio
async def test_exhausted_before_any_tier_stops_and_records(tmp_path, monkeypatch):
    events: list[tuple[str, dict]] = []
    monkeypatch.setattr(
        "daari.gateway.request_log.log_gateway_event",
        lambda event, payload: events.append((event, payload)),
    )
    frontier = _Frontier()
    calls: list[str] = []
    router = _router(tmp_path, deadline=None, calls=calls, frontier=frontier)
    request = InternalRequest(
        messages=[Message(role="user", content="need a bounded answer")],
        model="llama3.2:3b",
    )
    request.meta.deadline_ms = 0
    with pytest.raises(RequestDeadlineExceeded, match="deadline"):
        await router.route(request)
    assert calls == []
    assert frontier.calls == 0
    assert router.metrics.deadline_exhausted == 1
    matched = [payload for name, payload in events if name == "request_deadline_exceeded"]
    assert matched
    assert matched[-1]["tiers_attempted"] == []
    assert "elapsed_ms" in matched[-1]
    text = render_prometheus(router.metrics)
    assert "daari_request_deadline_exceeded_total 1" in text


@pytest.mark.asyncio
async def test_spent_budget_does_not_call_frontier(tmp_path, monkeypatch):
    clock = {"t": 0.0}
    monkeypatch.setattr("daari.router.deadline.time.monotonic", lambda: clock["t"])
    frontier = _Frontier()
    calls: list[str] = []

    def make_executor(tier: str) -> OllamaExecutor:
        executor = OllamaExecutor(
            base_url="http://test", default_model=f"model-{tier.lower()}", tier=tier
        )

        async def fake_execute(request: InternalRequest, _tier: str = tier) -> InternalResponse:
            calls.append(_tier)
            clock["t"] = 5.0
            return InternalResponse(
                content="no",
                model=executor.default_model,
                daari_meta=DaariMeta(tier=_tier, executor="ollama", latency_ms=1),
            )

        executor.execute = fake_execute  # type: ignore[method-assign]
        return executor

    router = Router(
        cache=ExactCache(str(tmp_path / "l0b"), enabled=True),
        semantic_cache=SemanticCache(
            path=str(tmp_path / "l1b"), embedder=NoopEmbedder(), enabled=False
        ),
        ollama_l3=make_executor("L3"),
        ollama_l4=make_executor("L4"),
        ollama_l5=make_executor("L5"),
        metrics=Metrics(),
        frontier=frontier,
        frontier_enabled=True,
        request_deadline_seconds=1.0,
    )
    request = InternalRequest(
        messages=[Message(role="user", content="escalate me")],
        model="llama3.2:3b",
    )
    response = await router.route(request)
    assert calls == ["L3"]
    assert frontier.calls == 0
    assert response.daari_meta.tier == "L3"
    assert response.daari_meta.warning == "request_deadline_exceeded"
    assert router.metrics.deadline_exhausted == 1


@pytest.mark.asyncio
async def test_absent_deadline_keeps_configured_httpx_timeout(monkeypatch):
    seen: list[float] = []

    class FakeClient:
        def __init__(self, **kwargs):
            seen.append(kwargs["timeout"])

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, *args, **kwargs):
            class Response:
                status_code = 200
                text = ""

                def json(self):
                    return {"message": {"content": "ok"}}

            return Response()

    monkeypatch.setattr("daari.router.router.httpx.AsyncClient", FakeClient)
    executor = OllamaExecutor(base_url="http://test", default_model="llama3.2:3b", timeout=120.0)
    await executor.execute(
        InternalRequest(messages=[Message(role="user", content="hi")], model="llama3.2:3b")
    )
    assert seen == [120.0]


@pytest.mark.asyncio
async def test_gateway_deadline_header_is_504(tmp_path):
    settings = Settings.model_validate(
        {
            "models": {"l3": "llama3.2:3b"},
            "cache": {"l0": {"enabled": False, "path": str(tmp_path / "l0")}},
            "upstream": {"request_deadline_seconds": 30},
        }
    )
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    called = {"n": 0}

    async def explode(request: InternalRequest) -> InternalResponse:
        called["n"] += 1
        raise AssertionError("upstream should not run")

    for name in ("ollama_l3", "ollama_l4", "ollama_l5"):
        setattr(getattr(app.state.ctx.router, name), "execute", explode)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/v1/chat/completions",
            json={"model": "daari", "messages": [{"role": "user", "content": "bound"}]},
            headers={"X-Daari-Deadline-Ms": "0", "X-Daari-No-Cache": "true"},
        )
    assert response.status_code == 504
    body = response.json()["error"]
    assert body["type"] == "request_deadline_exceeded"
    assert "deadline" in body["message"]
    assert body["deadline_seconds"] == 0
    assert called["n"] == 0
    assert app.state.ctx.metrics.deadline_exhausted == 1
