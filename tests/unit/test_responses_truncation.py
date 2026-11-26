"""Responses truncation auto/disabled (#2215)."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from daari.gateway.internal import DaariMeta, InternalRequest, InternalResponse, Message
from daari.gateway.sampling import SamplingParams
from daari.router.frontier import FrontierExecutor
from daari.router.router import AppContext
from daari.server.app import create_app


def _app(settings):
    application = create_app(settings)
    application.state.ctx = AppContext.from_settings(settings)
    return application


def _mock_route(app, *, tier="L3", executor="ollama", content="ok"):
    async def fake_route(request: InternalRequest) -> InternalResponse:
        fake_route.last_request = request
        meta = DaariMeta(tier=tier, executor=executor, latency_ms=1)
        if request.meta.compact_to_fit:
            meta.compact_to_fit = dict(request.meta.compact_to_fit)
        return InternalResponse(content=content, model="m", daari_meta=meta)

    app.state.ctx.router.route = fake_route
    return fake_route


def _tiny_windows(app, *, l3: int = 40) -> None:
    app.state.ctx.router.context_windows = {"L3": l3, "L4": 200, "L5": 1000}


def _oversized_input(*, chars: int = 400) -> str:
    return "x" * chars


def test_from_responses_body_keeps_auto_and_disabled(monkeypatch):
    events: list[tuple[str, dict]] = []
    monkeypatch.setattr(
        "daari.gateway.request_log.log_gateway_event",
        lambda event, payload: events.append((event, payload)),
    )
    auto = SamplingParams.from_responses_body({"truncation": "auto"})
    disabled = SamplingParams.from_responses_body({"truncation": "disabled"})
    omitted = SamplingParams.from_responses_body({"max_output_tokens": 8})
    assert auto.truncation == "auto"
    assert disabled.truncation == "disabled"
    assert omitted.truncation is None
    assert not any(name == "responses_truncation_ignored" for name, _ in events)


def test_unsupported_truncation_is_logged(monkeypatch):
    events: list[tuple[str, dict]] = []
    monkeypatch.setattr(
        "daari.gateway.request_log.log_gateway_event",
        lambda event, payload: events.append((event, payload)),
    )
    params = SamplingParams.from_responses_body({"truncation": "middle_out"})
    assert params.truncation is None
    assert any(name == "responses_truncation_ignored" for name, _ in events)


def test_openai_responses_payload_forwards_truncation():
    request = InternalRequest(
        messages=[Message(role="user", content="continue")],
        model="gpt-5.4",
        sampling=SamplingParams(
            truncation="auto",
            max_tokens=32,
            thinking={"type": "enabled"},
        ),
    )
    executor = FrontierExecutor(
        api_key="sk-test",
        base_url="https://api.openai.com/v1",
        default_model="gpt-5.4",
        provider="openai",
    )
    assert executor._uses_openai_responses_encrypted(request)
    payload = executor._openai_responses_payload(request, stream=False)
    assert payload["truncation"] == "auto"
    # Chat completions payload must not grow a Responses-only field.
    chat = executor._openai_payload(request, stream=False)
    assert "truncation" not in chat


@pytest.mark.asyncio
async def test_disabled_over_window_returns_context_length_exceeded(settings):
    app = _app(settings)
    _tiny_windows(app, l3=40)
    fake = _mock_route(app)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/responses",
            json={
                "model": "daari",
                "input": _oversized_input(),
                "truncation": "disabled",
            },
        )
    assert response.status_code == 400
    body = response.json()
    err = body.get("error") or {}
    assert err.get("code") == "context_length_exceeded"
    assert err.get("type") == "invalid_request_error"
    assert not hasattr(fake, "last_request")


@pytest.mark.asyncio
async def test_omitted_truncation_defaults_to_disabled(settings):
    app = _app(settings)
    _tiny_windows(app, l3=40)
    _mock_route(app)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/responses",
            json={"model": "daari", "input": _oversized_input()},
        )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "context_length_exceeded"


@pytest.mark.asyncio
async def test_auto_over_window_compacts_and_reports_meta(settings):
    app = _app(settings)
    _tiny_windows(app, l3=40)
    fake = _mock_route(app)
    # Multiple turns so compact_to_fit can drop oldest unprotected messages.
    turns = [{"role": "user", "content": f"turn-{i} " + ("y" * 80)} for i in range(8)]
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/responses",
            json={"model": "daari", "input": turns, "truncation": "auto"},
            headers={"X-Daari-Meta": "true"},
        )
    assert response.status_code == 200, response.text
    body = response.json()
    compact = body["daari_meta"]["compact_to_fit"]
    assert compact["messages_after"] < compact["messages_before"]
    assert len(fake.last_request.messages) == compact["messages_after"]


@pytest.mark.asyncio
async def test_auto_within_window_is_noop(settings):
    app = _app(settings)
    _tiny_windows(app, l3=10_000)
    fake = _mock_route(app)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/responses",
            json={"model": "daari", "input": "short", "truncation": "auto"},
            headers={"X-Daari-Meta": "true"},
        )
    assert response.status_code == 200
    assert response.json()["daari_meta"].get("compact_to_fit") is None
    assert len(fake.last_request.messages) == 1


@pytest.mark.asyncio
async def test_stream_disabled_over_window_returns_400(settings):
    app = _app(settings)
    _tiny_windows(app, l3=40)

    async def fake_chunks(request: InternalRequest):
        yield 'data: {"choices":[{"delta":{"content":"x"}}]}\n\n'
        yield "data: [DONE]\n\n"

    app.state.ctx.router.stream_openai_chunks = fake_chunks
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/responses",
            json={
                "model": "daari",
                "input": _oversized_input(),
                "truncation": "disabled",
                "stream": True,
            },
        )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "context_length_exceeded"


@pytest.mark.asyncio
async def test_stream_auto_compacts_before_stream(settings):
    app = _app(settings)
    _tiny_windows(app, l3=40)
    seen: list[InternalRequest] = []

    async def fake_chunks(request: InternalRequest):
        seen.append(request)
        yield 'data: {"choices":[{"delta":{"content":"hi"}}]}\n\n'
        yield "data: [DONE]\n\n"

    app.state.ctx.router.stream_openai_chunks = fake_chunks
    turns = [{"role": "user", "content": f"s{i} " + ("z" * 80)} for i in range(8)]
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/responses",
            json={"model": "daari", "input": turns, "truncation": "auto", "stream": True},
        )
    assert response.status_code == 200
    assert "response.completed" in response.text or "response.output_text.delta" in response.text
    assert seen
    assert len(seen[0].messages) < 8
    assert seen[0].meta.compact_to_fit is not None
    assert seen[0].meta.compact_to_fit["messages_after"] < seen[0].meta.compact_to_fit[
        "messages_before"
    ]


@pytest.mark.asyncio
async def test_frontier_disabled_uses_l6_window_when_configured(settings):
    """Frontier-shaped route still enforces when a window is known (#2215)."""
    app = _app(settings)
    app.state.ctx.router.context_windows = {"L3": 40, "L4": 40, "L5": 40, "L6": 40}
    fake = _mock_route(app, tier="L6", executor="openai")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/responses",
            json={
                "model": "daari",
                "input": _oversized_input(),
                "truncation": "disabled",
            },
            headers={"X-Daari-Tier-Override": "L6"},
        )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "context_length_exceeded"
    assert not hasattr(fake, "last_request")


def _truncation_counts(app) -> tuple[int, int, int]:
    snap = app.state.ctx.metrics.snapshot(include_histograms=True)
    return (
        int(snap.get("responses_truncation_auto") or 0),
        int(snap.get("responses_truncation_rejected") or 0),
        int(snap.get("responses_truncation_tokens_dropped") or 0),
    )


@pytest.mark.asyncio
async def test_auto_compaction_increments_truncation_counters(settings):
    """Successful ``truncation: auto`` increments auto + tokens dropped (#2306)."""
    from daari.observability.prometheus import render_prometheus

    app = _app(settings)
    _tiny_windows(app, l3=40)
    _mock_route(app)
    assert _truncation_counts(app) == (0, 0, 0)
    turns = [{"role": "user", "content": f"turn-{i} " + ("y" * 80)} for i in range(8)]
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/responses",
            json={"model": "daari", "input": turns, "truncation": "auto"},
            headers={"X-Daari-Meta": "true"},
        )
    assert response.status_code == 200, response.text
    compact = response.json()["daari_meta"]["compact_to_fit"]
    auto, rejected, dropped = _truncation_counts(app)
    assert auto == 1
    assert rejected == 0
    assert dropped == compact["tokens_before"] - compact["tokens_after"] > 0
    text = render_prometheus(app.state.ctx.metrics)
    assert "daari_responses_truncation_auto_total 1" in text
    assert f"daari_responses_truncation_tokens_dropped_total {dropped}" in text
    assert "daari_responses_truncation_rejected_total 0" in text


@pytest.mark.asyncio
async def test_disabled_reject_increments_rejected_counter(settings):
    """``context_length_exceeded`` 400 increments rejected only (#2306)."""
    from daari.observability.prometheus import render_prometheus

    app = _app(settings)
    _tiny_windows(app, l3=40)
    _mock_route(app)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        disabled = await client.post(
            "/v1/responses",
            json={"model": "daari", "input": _oversized_input(), "truncation": "disabled"},
        )
        omitted = await client.post(
            "/v1/responses",
            json={"model": "daari", "input": _oversized_input()},
        )
    for response in (disabled, omitted):
        assert response.status_code == 400
        assert response.json()["error"]["code"] == "context_length_exceeded"
    assert _truncation_counts(app) == (0, 2, 0)
    text = render_prometheus(app.state.ctx.metrics)
    assert "daari_responses_truncation_rejected_total 2" in text
    assert "daari_responses_truncation_auto_total 0" in text


@pytest.mark.asyncio
async def test_within_window_leaves_truncation_counters_at_zero(settings):
    app = _app(settings)
    _tiny_windows(app, l3=10_000)
    _mock_route(app)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/responses",
            json={"model": "daari", "input": "short", "truncation": "auto"},
        )
    assert response.status_code == 200
    assert _truncation_counts(app) == (0, 0, 0)


@pytest.mark.asyncio
async def test_stats_exposes_responses_truncation_counters(settings):
    app = _app(settings)
    _tiny_windows(app, l3=40)
    _mock_route(app)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        before = await client.get("/v1/daari/stats")
        assert before.status_code == 200
        assert before.json()["responses_truncation_auto"] == 0
        assert before.json()["responses_truncation_rejected"] == 0
        assert before.json()["responses_truncation_tokens_dropped"] == 0
        rejected = await client.post(
            "/v1/responses",
            json={"model": "daari", "input": _oversized_input(), "truncation": "disabled"},
        )
        assert rejected.status_code == 400
        turns = [{"role": "user", "content": f"t{i} " + ("y" * 80)} for i in range(8)]
        compacted = await client.post(
            "/v1/responses",
            json={"model": "daari", "input": turns, "truncation": "auto"},
        )
        assert compacted.status_code == 200, compacted.text
        after = await client.get("/v1/daari/stats")
    body = after.json()
    assert body["responses_truncation_auto"] == 1
    assert body["responses_truncation_rejected"] == 1
    assert body["responses_truncation_tokens_dropped"] > 0


def test_auto_still_over_window_after_compact_counts_as_rejected():
    """Unit-level: auto that cannot fit the window records rejected, not auto (#2306)."""
    from daari.gateway.responses_truncation import apply_responses_truncation
    from daari.observability.metrics import Metrics

    metrics = Metrics()
    request = InternalRequest(
        messages=[
            Message(role="system", content="s" * 400),
            Message(role="user", content="u" * 400),
        ],
        model="daari",
        sampling=SamplingParams(truncation="auto"),
    )
    _, error = apply_responses_truncation(
        request, context_windows={"L3": 40}, metrics=metrics
    )
    assert error is not None and error.status_code == 400
    snap = metrics.snapshot(include_histograms=True)
    assert snap["responses_truncation_rejected"] == 1
    assert snap["responses_truncation_auto"] == 0
    assert snap["responses_truncation_tokens_dropped"] == 0
