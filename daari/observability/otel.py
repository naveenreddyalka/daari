"""Optional OpenTelemetry export for RequestTrace steps (issues #115, #167).

Off by default. When enabled and `opentelemetry-api` is installed, each
finished RequestTrace is exported as a span tree. Missing OTel packages are
a no-op so the core daemon never hard-depends on them.

Spans and metrics follow the OpenTelemetry GenAI semantic conventions
(`gen_ai.*`), which are Development status as of v1.42.0 and may still shift;
daari-specific facts (tier, cache hit, escalation, boundary) stay under the
`daari.*` namespace. Token usage is only emitted when the provider reported
real counts (`usage_estimated` is False) so the attributes stay truthful.
"""

from __future__ import annotations

import os
from typing import Any

_MAX_ATTR_CHARS = 200

# Instrument cache keyed by meter-provider identity: the global provider is
# normally set once at startup, but tests (and re-configuration) may install
# a new one, and instruments created against the old provider would silently
# record nothing.
_instrument_cache: dict[int, dict[str, Any]] = {}


def configure_providers(service_name: str = "daari") -> bool:
    """Install OTLP-exporting tracer/meter providers at startup, best-effort.

    Only acts when `OTEL_EXPORTER_OTLP_ENDPOINT` is set (so a bare
    `observability.otel: true` never spams connection errors at a default
    endpoint nobody runs) and when no real SDK provider is installed yet —
    a host app or `opentelemetry-instrument` wrapper always wins. Returns
    True only when this call installed the providers.
    """
    if not os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT"):
        return False
    try:
        from opentelemetry import metrics as otel_metrics
        from opentelemetry import trace as otel_trace
        from opentelemetry.exporter.otlp.proto.http.metric_exporter import (
            OTLPMetricExporter,
        )
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
            OTLPSpanExporter,
        )
        from opentelemetry.sdk.metrics import MeterProvider
        from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
    except ImportError:
        return False
    try:
        if isinstance(otel_trace.get_tracer_provider(), TracerProvider):
            return False
        resource = Resource.create({"service.name": service_name})
        tracer_provider = TracerProvider(resource=resource)
        tracer_provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
        otel_trace.set_tracer_provider(tracer_provider)
        otel_metrics.set_meter_provider(
            MeterProvider(
                resource=resource,
                metric_readers=[PeriodicExportingMetricReader(OTLPMetricExporter())],
            )
        )
        return True
    except Exception:
        return False


def _attr_value(value: Any) -> Any:
    """Numbers and bools pass through natively (#167); the rest stringify."""
    if isinstance(value, bool) or isinstance(value, (int, float)):
        return value
    return str(value)[:_MAX_ATTR_CHARS]


def _provider_name(response: Any) -> str | None:
    meta = getattr(response, "daari_meta", None)
    if meta is None:
        return None
    provider_id = getattr(meta, "provider_id", None)
    if provider_id:
        return str(provider_id).split(":", 1)[0]
    executor = getattr(meta, "executor", None)
    return str(executor) if executor else None


def _instruments() -> dict[str, Any] | None:
    try:
        from opentelemetry import metrics as otel_metrics
    except ImportError:
        return None
    provider = otel_metrics.get_meter_provider()
    cached = _instrument_cache.get(id(provider))
    if cached is None:
        meter = otel_metrics.get_meter("daari")
        cached = {
            "token_usage": meter.create_histogram(
                "gen_ai.client.token.usage",
                unit="{token}",
                description="Number of input and output tokens used per operation",
            ),
            "duration": meter.create_histogram(
                "gen_ai.client.operation.duration",
                unit="s",
                description="GenAI operation duration",
            ),
            "time_to_first_token": meter.create_histogram(
                "gen_ai.server.time_to_first_token",
                unit="s",
                description="Time to first streamed chunk",
            ),
            "time_per_output_token": meter.create_histogram(
                "gen_ai.server.time_per_output_token",
                unit="s",
                description="Mean time per streamed output chunk after the first",
            ),
        }
        _instrument_cache.clear()
        _instrument_cache[id(provider)] = cached
    return cached


def _duration_seconds(trace: Any, response: Any) -> float | None:
    meta = getattr(response, "daari_meta", None)
    latency_ms = getattr(meta, "latency_ms", 0) if meta is not None else 0
    if latency_ms:
        return latency_ms / 1000.0
    steps = getattr(trace, "steps", None) or []
    if steps:
        elapsed = steps[-1].get("elapsed_ms")
        if elapsed:
            return elapsed / 1000.0
    return None


def _record_metrics(
    *,
    trace: Any,
    response: Any,
    metric_attrs: dict[str, Any],
    usage: tuple[int | None, int | None],
    time_to_first_chunk: float | None,
    time_per_output_chunk: float | None,
) -> None:
    instruments = _instruments()
    if instruments is None:
        return
    input_tokens, output_tokens = usage
    if input_tokens is not None:
        instruments["token_usage"].record(
            input_tokens, attributes={**metric_attrs, "gen_ai.token.type": "input"}
        )
    if output_tokens is not None:
        instruments["token_usage"].record(
            output_tokens, attributes={**metric_attrs, "gen_ai.token.type": "output"}
        )
    duration = _duration_seconds(trace, response)
    if duration is not None:
        instruments["duration"].record(duration, attributes=metric_attrs)
    if time_to_first_chunk is not None:
        instruments["time_to_first_token"].record(
            time_to_first_chunk, attributes=metric_attrs
        )
    if time_per_output_chunk is not None:
        instruments["time_per_output_token"].record(
            time_per_output_chunk, attributes=metric_attrs
        )


def export_trace(
    trace: Any,
    *,
    service_name: str = "daari",
    request: Any = None,
    response: Any = None,
    error_type: str | None = None,
    time_to_first_chunk: float | None = None,
    time_per_output_chunk: float | None = None,
) -> bool:
    """Best-effort export. Returns True if a span was exported.

    With `request`/`response` context the root span follows the GenAI
    conventions (`chat {model}` + `gen_ai.*`); without it the legacy
    `daari.request.{id}` shape is kept for callers that predate #167.
    """
    try:
        from opentelemetry import trace as otel_trace
    except ImportError:
        return False
    try:
        request_model = getattr(request, "model", None)
        meta = getattr(response, "daari_meta", None)

        root_attrs: dict[str, Any] = {"daari.trace_id": getattr(trace, "trace_id", "")}
        usage: tuple[int | None, int | None] = (None, None)
        metric_attrs: dict[str, Any] = {}
        if request_model:
            span_name = f"chat {request_model}"
            root_attrs["gen_ai.operation.name"] = "chat"
            root_attrs["gen_ai.request.model"] = str(request_model)
            metric_attrs = {
                "gen_ai.operation.name": "chat",
                "gen_ai.request.model": str(request_model),
            }
            provider = _provider_name(response)
            if provider:
                root_attrs["gen_ai.provider.name"] = provider
                metric_attrs["gen_ai.provider.name"] = provider
            response_model = getattr(response, "model", None) or (
                getattr(meta, "model", None) if meta is not None else None
            )
            if response_model:
                root_attrs["gen_ai.response.model"] = str(response_model)
                metric_attrs["gen_ai.response.model"] = str(response_model)
            finish_reason = getattr(response, "finish_reason", None)
            if finish_reason:
                root_attrs["gen_ai.response.finish_reasons"] = [str(finish_reason)]
            if meta is not None:
                estimated = bool(getattr(meta, "usage_estimated", True))
                root_attrs["daari.usage_estimated"] = estimated
                if not estimated:
                    input_tokens = getattr(meta, "input_tokens", None)
                    output_tokens = getattr(meta, "output_tokens", None)
                    usage = (
                        int(input_tokens) if input_tokens is not None else None,
                        int(output_tokens) if output_tokens is not None else None,
                    )
                    if usage[0] is not None:
                        root_attrs["gen_ai.usage.input_tokens"] = usage[0]
                    if usage[1] is not None:
                        root_attrs["gen_ai.usage.output_tokens"] = usage[1]
                for fact in ("tier", "cache_hit", "backend_id", "escalated_from"):
                    value = getattr(meta, fact, None)
                    if value is not None:
                        root_attrs[f"daari.{fact}"] = _attr_value(value)
        else:
            span_name = f"daari.request.{getattr(trace, 'trace_id', '')}"
        if error_type:
            root_attrs["error.type"] = str(error_type)

        tracer = otel_trace.get_tracer(service_name)
        with tracer.start_as_current_span(span_name) as span:
            for key, value in root_attrs.items():
                span.set_attribute(key, value)
            for step in getattr(trace, "steps", []) or []:
                name = step.get("step", "step")
                with tracer.start_as_current_span(name) as child:
                    detail = step.get("detail") or {}
                    for key, value in detail.items():
                        child.set_attribute(f"daari.{key}", _attr_value(value))
                    if "elapsed_ms" in step:
                        child.set_attribute("daari.elapsed_ms", int(step["elapsed_ms"]))
        if request_model:
            _record_metrics(
                trace=trace,
                response=response,
                metric_attrs=metric_attrs,
                usage=usage,
                time_to_first_chunk=time_to_first_chunk,
                time_per_output_chunk=time_per_output_chunk,
            )
        return True
    except Exception:
        return False
