"""OTel GenAI semantic conventions (issue #167).

Spans are named ``chat {model}`` and carry ``gen_ai.*`` attributes per the
OpenTelemetry GenAI semantic conventions; daari-specific facts stay under
``daari.*``. Metrics cover token usage, operation duration, and streaming
chunk timing. The conventions are Development status and may shift.
"""

from __future__ import annotations

import pytest

pytest.importorskip("opentelemetry.sdk")

from opentelemetry import metrics as otel_metrics  # noqa: E402
from opentelemetry import trace as otel_trace  # noqa: E402
from opentelemetry.sdk.metrics import MeterProvider  # noqa: E402
from opentelemetry.sdk.metrics.export import InMemoryMetricReader  # noqa: E402
from opentelemetry.sdk.trace import TracerProvider  # noqa: E402
from opentelemetry.sdk.trace.export import SimpleSpanProcessor  # noqa: E402
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (  # noqa: E402
    InMemorySpanExporter,
)

from daari.gateway.internal import DaariMeta, InternalRequest, InternalResponse, Message  # noqa: E402
from daari.observability.otel import (  # noqa: E402
    configure_providers,
    export_trace,
    extract_inbound_context,
    inject_trace_headers,
    reset_inbound_context,
)
from daari.observability.trace import RequestTrace  # noqa: E402
from opentelemetry.trace.propagation.tracecontext import (  # noqa: E402
    TraceContextTextMapPropagator,
)

_EXPORTER = InMemorySpanExporter()
_READER = InMemoryMetricReader()


@pytest.fixture(scope="module", autouse=True)
def _providers():
    # Global OTel providers can only be set once per process, so one shared
    # exporter/reader pair serves every test in this module.
    tracer_provider = TracerProvider()
    tracer_provider.add_span_processor(SimpleSpanProcessor(_EXPORTER))
    otel_trace.set_tracer_provider(tracer_provider)
    otel_metrics.set_meter_provider(MeterProvider(metric_readers=[_READER]))
    yield


@pytest.fixture(autouse=True)
def _clear_spans():
    _EXPORTER.clear()
    token = extract_inbound_context({})
    reset_inbound_context(token)
    yield
    reset_inbound_context(extract_inbound_context({}))


def _request(model: str = "llama3.2:3b") -> InternalRequest:
    return InternalRequest(messages=[Message(role="user", content="hi")], model=model)


def _response(
    *,
    model: str = "llama3.2:3b",
    finish_reason: str = "stop",
    input_tokens: int | None = 120,
    output_tokens: int | None = 45,
    usage_estimated: bool = False,
    executor: str = "ollama",
    provider_id: str | None = "ollama:l3",
    latency_ms: int = 250,
    agent_turn: bool | None = None,
) -> InternalResponse:
    return InternalResponse(
        content="hello",
        model=model,
        finish_reason=finish_reason,
        daari_meta=DaariMeta(
            tier="L3",
            executor=executor,
            provider_id=provider_id,
            model=model,
            latency_ms=latency_ms,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            usage_estimated=usage_estimated,
            agent_turn=agent_turn,
        ),
    )


def _root_span():
    spans = _EXPORTER.get_finished_spans()
    roots = [span for span in spans if span.parent is None]
    assert len(roots) == 1, f"expected one root span, got {[s.name for s in roots]}"
    return roots[0]


def _metric_points(name: str):
    data = _READER.get_metrics_data()
    points = []
    for resource_metrics in data.resource_metrics:
        for scope_metrics in resource_metrics.scope_metrics:
            for metric in scope_metrics.metrics:
                if metric.name == name:
                    points.extend(metric.data.data_points)
    return points


def test_chat_span_name_and_genai_attributes():
    trace = RequestTrace()
    trace.add("tier_attempt", tier="L3")
    assert export_trace(trace, request=_request(), response=_response()) is True

    root = _root_span()
    assert root.name == "chat llama3.2:3b"
    attrs = dict(root.attributes)
    assert attrs["gen_ai.operation.name"] == "chat"
    assert attrs["gen_ai.provider.name"] == "ollama"
    assert attrs["gen_ai.request.model"] == "llama3.2:3b"
    assert attrs["gen_ai.response.model"] == "llama3.2:3b"
    assert tuple(attrs["gen_ai.response.finish_reasons"]) == ("stop",)
    assert attrs["gen_ai.usage.input_tokens"] == 120
    assert isinstance(attrs["gen_ai.usage.input_tokens"], int)
    assert attrs["gen_ai.usage.output_tokens"] == 45


def test_estimated_usage_is_not_reported_as_genai():
    trace = RequestTrace()
    export_trace(
        trace,
        request=_request(),
        response=_response(usage_estimated=True),
    )
    attrs = dict(_root_span().attributes)
    assert "gen_ai.usage.input_tokens" not in attrs
    assert "gen_ai.usage.output_tokens" not in attrs
    assert attrs["daari.usage_estimated"] is True


def test_daari_step_attributes_keep_native_types():
    trace = RequestTrace()
    trace.add("served", tier="L3", cache_hit=False, latency_ms=42)
    export_trace(trace, request=_request(), response=_response())

    spans = {span.name: span for span in _EXPORTER.get_finished_spans()}
    served = spans["served"]
    attrs = dict(served.attributes)
    assert attrs["daari.tier"] == "L3"
    assert attrs["daari.latency_ms"] == 42
    assert isinstance(attrs["daari.latency_ms"], int)
    assert attrs["daari.cache_hit"] is False


def test_daari_facts_on_root_span():
    trace = RequestTrace()
    export_trace(trace, request=_request(), response=_response())
    attrs = dict(_root_span().attributes)
    assert attrs["daari.tier"] == "L3"
    assert attrs["daari.cache_hit"] is False
    assert attrs["daari.trace_id"] == trace.trace_id


def test_daari_agent_turn_on_root_span():
    """ADR-0004 agent_turn lands on the GenAI root span (#630)."""
    trace = RequestTrace()
    export_trace(trace, request=_request(), response=_response(agent_turn=True))
    assert dict(_root_span().attributes)["daari.agent_turn"] is True

    _EXPORTER.clear()
    export_trace(trace, request=_request(), response=_response(agent_turn=False))
    assert dict(_root_span().attributes)["daari.agent_turn"] is False

    _EXPORTER.clear()
    export_trace(trace, request=_request(), response=_response())
    assert "daari.agent_turn" not in dict(_root_span().attributes)


def test_error_type_attribute():
    trace = RequestTrace()
    export_trace(
        trace,
        request=_request(),
        error_type="BackendUnavailable",
    )
    attrs = dict(_root_span().attributes)
    assert attrs["error.type"] == "BackendUnavailable"


def test_legacy_call_without_context_still_works():
    trace = RequestTrace()
    trace.add("cache_hit")
    assert export_trace(trace) is True
    root = _root_span()
    assert root.name.startswith("daari.request.")


def test_token_usage_and_duration_metrics():
    trace = RequestTrace()
    export_trace(trace, request=_request(), response=_response())

    usage_points = _metric_points("gen_ai.client.token.usage")
    by_type = {p.attributes["gen_ai.token.type"]: p for p in usage_points}
    assert by_type["input"].sum >= 120
    assert by_type["output"].sum >= 45
    for point in usage_points:
        assert point.attributes["gen_ai.operation.name"] == "chat"
        assert point.attributes["gen_ai.provider.name"] == "ollama"

    duration_points = _metric_points("gen_ai.client.operation.duration")
    assert duration_points, "expected an operation duration histogram point"
    assert any(p.sum >= 0.25 for p in duration_points)


def test_stream_timing_metrics():
    trace = RequestTrace()
    export_trace(
        trace,
        request=_request(),
        response=_response(),
        time_to_first_chunk=0.25,
        time_per_output_chunk=0.02,
    )
    ttft = _metric_points("gen_ai.server.time_to_first_token")
    assert any(p.sum >= 0.25 for p in ttft)
    tpot = _metric_points("gen_ai.server.time_per_output_token")
    assert any(0.0 < p.sum <= 0.5 for p in tpot)


def test_configure_providers_requires_collector_endpoint(monkeypatch):
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
    assert configure_providers() is False


def test_configure_providers_defers_to_existing_provider(monkeypatch):
    # The module fixture already installed an SDK TracerProvider; startup
    # bootstrap must not fight a host that configured OTel first.
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://127.0.0.1:4318")
    assert configure_providers() is False


def test_export_never_raises_on_odd_input():
    trace = RequestTrace()
    trace.add("weird", payload={"nested": object()})
    assert isinstance(export_trace(trace, request=_request(), response=_response()), bool)


@pytest.mark.asyncio
async def test_router_route_exports_chat_span(settings, monkeypatch):
    from daari.router.router import AppContext

    settings.observability.otel = True
    ctx = AppContext.from_settings(settings)

    async def fake_execute(request: InternalRequest) -> InternalResponse:
        return _response(input_tokens=7, output_tokens=3)

    from tests.conftest import mock_all_ollama_executors

    mock_all_ollama_executors(monkeypatch, ctx.router, fake_execute)
    response = await ctx.router.route(
        InternalRequest(
            messages=[Message(role="user", content="otel genai span please")],
            model="llama3.2:3b",
            meta={"no_cache": True},
        )
    )
    assert response.daari_meta.tier in {"L3", "L4", "L5"}

    root = _root_span()
    assert root.name == "chat llama3.2:3b"
    attrs = dict(root.attributes)
    assert attrs["gen_ai.usage.input_tokens"] == 7
    assert attrs["daari.tier"] in {"L3", "L4", "L5"}


@pytest.mark.asyncio
async def test_router_stream_exports_span_and_timing_metrics(settings, monkeypatch):
    from daari.router.router import AppContext

    settings.observability.otel = True
    ctx = AppContext.from_settings(settings)

    async def fake_stream(request: InternalRequest):
        yield {"message": {"content": "hel"}}
        yield {"message": {"content": "lo there"}}
        yield {
            "message": {"content": ""},
            "done": True,
            "prompt_eval_count": 11,
            "eval_count": 4,
        }

    monkeypatch.setattr(ctx.router.ollama, "stream", fake_stream)
    chunks = [
        chunk
        async for chunk in ctx.router.stream_openai_chunks(
            InternalRequest(
                messages=[Message(role="user", content="stream otel timing")],
                model="llama3.2:3b",
                stream=True,
                meta={"no_cache": True},
            )
        )
    ]
    assert any("[DONE]" in chunk for chunk in chunks)

    roots = [s for s in _EXPORTER.get_finished_spans() if s.parent is None]
    chat_roots = [s for s in roots if s.name == "chat llama3.2:3b"]
    assert chat_roots, f"no chat root span, got {[s.name for s in roots]}"
    attrs = dict(chat_roots[-1].attributes)
    assert attrs["gen_ai.usage.input_tokens"] == 11
    assert attrs["gen_ai.usage.output_tokens"] == 4
    assert _metric_points("gen_ai.server.time_to_first_token")


def _client_carrier() -> tuple[dict[str, str], object]:
    """Start a client span and inject W3C headers (simulates the caller)."""
    tracer = otel_trace.get_tracer("client-app")
    with tracer.start_as_current_span("client.op") as span:
        carrier: dict[str, str] = {}
        TraceContextTextMapPropagator().inject(carrier)
        return carrier, span.get_span_context()


def test_export_parented_to_inbound_traceparent():
    carrier, parent_ctx = _client_carrier()
    assert "traceparent" in carrier
    token = extract_inbound_context(carrier)
    try:
        trace = RequestTrace()
        trace.add("tier_attempt", tier="L3")
        assert export_trace(trace, request=_request(), response=_response()) is True
    finally:
        reset_inbound_context(token)

    chat = [s for s in _EXPORTER.get_finished_spans() if s.name == "chat llama3.2:3b"]
    assert len(chat) == 1
    child = chat[0]
    assert child.parent is not None
    assert child.parent.trace_id == parent_ctx.trace_id
    assert child.parent.span_id == parent_ctx.span_id
    assert child.context.trace_id == parent_ctx.trace_id


def test_tracestate_preserved_on_inject():
    parent = "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"
    state = "rojo=00f067aa0ba902b7,congo=t61rcWkgMzE"
    token = extract_inbound_context({"traceparent": parent, "tracestate": state})
    try:
        out = inject_trace_headers({})
    finally:
        reset_inbound_context(token)
    assert out.get("traceparent") == parent
    assert out.get("tracestate") == state


def test_inject_noop_without_inbound_context():
    assert inject_trace_headers({"Authorization": "Bearer x"}) == {
        "Authorization": "Bearer x"
    }


def test_export_without_inbound_still_root():
    trace = RequestTrace()
    assert export_trace(trace, request=_request(), response=_response()) is True
    roots = [s for s in _EXPORTER.get_finished_spans() if s.parent is None]
    assert any(s.name == "chat llama3.2:3b" for s in roots)


@pytest.mark.asyncio
async def test_frontier_injects_traceparent(monkeypatch):
    from daari.router.frontier import FrontierExecutor

    carrier, _parent = _client_carrier()
    token = extract_inbound_context(carrier)
    seen: list[dict] = []

    class _Resp:
        status_code = 200

        def json(self):
            return {
                "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1},
            }

        def raise_for_status(self):
            return None

    class _Client:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return None

        async def post(self, path, json=None, headers=None, **kwargs):
            seen.append(dict(headers or {}))
            return _Resp()

    monkeypatch.setattr("daari.router.frontier.httpx.AsyncClient", _Client)
    try:
        executor = FrontierExecutor(
            api_key="sk-test",
            base_url="https://api.openai.com/v1",
            default_model="gpt-4o-mini",
        )
        await executor.execute(
            InternalRequest(
                messages=[Message(role="user", content="hi")],
                model="gpt-4o-mini",
            ),
            escalated_from="L3",
            local_confidence=0.5,
        )
    finally:
        reset_inbound_context(token)

    assert seen
    assert "traceparent" in seen[0]
