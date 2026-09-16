# Prometheus metrics

**Outcome:** Scrape `GET /metrics` for tier and boundary counters.

## Steps

Enable exposition (see config `observability` / prometheus flags in reference). Scrape:

```bash
curl -s http://127.0.0.1:11435/metrics | head
```

Import Grafana dashboard: `deploy/grafana/daari-dashboard.json` (includes a
**TTFT p50 / p95 by tier** panel on `daari_ttft_ms` for stream startup health,
a **Soft warnings by kind** panel on `daari_soft_warnings_total` for soft-band
pressure before hard 402/429, and a **Hard rejects by kind** panel on
`daari_rejects_total` for cliffs after the soft band).

Useful series: request latency histograms by tier (`daari_request_latency_ms`),
stream time-to-first-token histograms by tier (`daari_ttft_ms` — stream path
only; non-stream omits TTFT), `daari_guardrail_trips_total`,
`daari_boundary_decisions_total`.

Two counters worth alerting on:

| Series | Reading it |
|--------|-----------|
| `daari_upstream_retries_total` | Transient upstream failures absorbed by backoff. Rising here while errors stay flat means clients never saw the instability. Rising alongside errors means the failures are not retryable — check for 401s or malformed requests. |
| `daari_cache_false_hits_avoided_total` | L1 hits vetoed by verification. Steady growth is the cache working; a spike suggests the similarity threshold is too loose. |
| `daari_soft_warnings_total{kind}` | Soft-band pressure before hard rejects: `kind="request_quota"` (`x-daari-quota-requests-warning`) or `kind="rate_limit"` (`x-daari-ratelimit-warning`). Rising here while 402/429 stay flat means agents are hovering in the soft band — scale Ollama or widen caps before hard rejects start. Hard 402/429 do not increment this counter. |
| `daari_rejects_total{kind}` | Hard denials only: `kind="budget"` (USD 402), `kind="request_quota"` (request-cap 402), or `kind="rate_limit"` (429). Soft warning headers never increment this. Rising rejects after soft warnings means caps are undersized relative to demand. |

Retries also appear per-request as `upstream_retry` trace steps with the status and
delay, so a slow request explains its own latency. See
[traces](traces-stats.md) and `upstream.*` in the
[config reference](../../reference/config.md).

## Next

→ [Config reference](../../reference/config.md)
