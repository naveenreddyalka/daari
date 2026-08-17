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
`daari.cache_hit`, `daari.backend_id`, `daari.escalated_from`, plus one child
span per routing step (`profile`, `tier_attempt`, `backend_pick`, `served`,
…) with its detail fields.

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
