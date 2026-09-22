# OpenTelemetry GenAI traces

daari can export each request as an OpenTelemetry span tree following the
[GenAI semantic conventions](https://opentelemetry.io/docs/specs/semconv/gen-ai/),
so traces join whatever your Langfuse, Grafana, or Datadog dashboards already
key on.

!!! note "Development-status conventions"
    The `gen_ai.*` conventions are **Development** status (moved to
    `open-telemetry/semantic-conventions-genai` in v1.42.0). daari tracks
    them as they stand; attribute names may shift in future releases.

## Enable

```bash
pip install "daari[otel]"
```

```yaml
observability:
  otel: true
```

```bash
OTEL_EXPORTER_OTLP_ENDPOINT=http://127.0.0.1:4318 daari serve
```

At startup daari installs OTLP-exporting tracer and meter providers, but only
when `OTEL_EXPORTER_OTLP_ENDPOINT` is set (no collector, no connection spam)
and when nothing else configured OTel first — running under
`opentelemetry-instrument` or embedding daari in an app that owns the SDK
both win.

## What gets emitted

Each routed request becomes a root span named `chat {model}` carrying:

| Attribute | Example |
|-----------|---------|
| `gen_ai.operation.name` | `chat` |
| `gen_ai.provider.name` | `ollama`, `openai`, `anthropic` |
| `gen_ai.request.model` / `gen_ai.response.model` | `llama3.2:3b` |
| `gen_ai.response.finish_reasons` | `["stop"]` |
| `gen_ai.usage.input_tokens` / `gen_ai.usage.output_tokens` | `120` / `45` |
| `error.type` | `BackendUnavailable` (failures only) |

Token usage attributes appear **only when the provider reported real counts**
(`daari.usage_estimated` is `false`); estimated counts are never passed off
as measurements. Numeric attributes are numbers, not strings.

daari-specific facts stay under the `daari.*` namespace — `daari.tier`,
`daari.cache_hit`, `daari.backend_id`, `daari.escalated_from`,
`daari.agent_turn` (ADR-0004), plus one child span per routing step
(`profile`, `tier_attempt`, `backend_pick`, `served`, …) with its detail
fields.

Metrics, per the conventions:

- `gen_ai.client.token.usage` — histogram, `gen_ai.token.type` = `input`/`output`
- `gen_ai.client.operation.duration` — histogram, seconds
- `gen_ai.server.time_to_first_token` and `gen_ai.server.time_per_output_token`
  — streaming only: time to the first chunk and mean time per subsequent chunk

## Verify locally

```bash
python scripts/smoke_otel_genai.py
```

boots an in-process OTLP collector, routes a request, and prints the spans,
`gen_ai.*` attributes, and metric names that actually arrived over the wire.

## Trace-context propagation

When a caller sends W3C `traceparent` (and optional `tracestate`), daari
parents its GenAI span tree under that context and injects the same headers on
outbound calls to Ollama, OpenAI-compat, MLX, and frontier providers. One
request then appears as a single trace in Jaeger/Tempo — client → daari
routing steps → provider — instead of three disconnected trees.

Propagation is a no-op when `observability.otel` is off or the
`opentelemetry` packages are missing (same guard pattern as export).

```bash
# Caller starts a span, then:
curl -H "traceparent: 00-<trace-id>-<span-id>-01" \
  http://127.0.0.1:11435/v1/chat/completions ...
```

In your collector, filter by that `trace-id`: the `chat {model}` span and its
`tier_attempt` / `served` children sit under the caller's span, and upstream
provider spans (when the backend honors `traceparent`) share the same id.

## OTLP logs (gateway events)

Gateway request events (`log_gateway_event`) always write JSONL to
`~/.daari/cursor-requests.log` and optionally mirror to stdout via
`observability.structured_json_logs`. To also ship them on the same OTLP pipe
as traces and metrics (Datadog / Splunk / Loki via your collector):

```yaml
observability:
  otlp_logs: true
```

```bash
OTEL_EXPORTER_OTLP_ENDPOINT=http://127.0.0.1:4318 daari serve
```

Requires the optional `daari[otel]` extra. Each event becomes an OTel
`LogRecord` with `event_name` set to the gateway event and payload fields as
attributes (`daari.event` plus the original keys). When a request already has
an active span or inbound `traceparent`, the log record carries that
trace/span id so it joins the GenAI tree in the collector.

Collector unavailability fails open — request handling never blocks or errors
on log export. File JSONL and stdout mirror behavior are unchanged.

