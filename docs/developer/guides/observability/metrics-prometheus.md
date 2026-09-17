# Prometheus metrics

**Outcome:** Scrape `GET /metrics` for tier and boundary counters.

## Steps

Enable exposition (see config `observability` / prometheus flags in reference). Scrape:

```bash
curl -s http://127.0.0.1:11435/metrics | head
```

When `server.api_key` is set, that scrape needs `Authorization: Bearer …`. For a
private scrape network, set `observability.metrics_port` (e.g. `9090`) so daari
also binds `127.0.0.1:<port>/metrics` **without** API key auth — keep that port
off public ingress. Main-port `/metrics` auth is unchanged.

Import Grafana dashboard: `deploy/grafana/daari-dashboard.json` (includes a
**TTFT p50 / p95 by tier** panel on `daari_ttft_ms` for stream startup health,
a **Soft warnings by kind** panel on `daari_soft_warnings_total` for soft-band
pressure before hard 402/429, a **Hard rejects by kind** panel on
`daari_rejects_total` for cliffs after the soft band, a **Rate-limit Redis
degraded** panel on `daari_rate_limit_degraded` for shared-counter fallback,
a **TTFT preference by from→to** panel on `daari_ttft_preference_total`
for TTFT-aware local tier bias, a **Backend pool health & outstanding**
panel on `daari_backend_up` / `daari_backend_outstanding` (and request rate),
a **Concurrency gate** panel on `daari_rate_limit_in_flight` vs
`_in_flight_max` / `_queued`, alert-series panels for
`daari_upstream_retries_total`, `daari_cache_false_hits_avoided_total`, and
`daari_budget_alerts_total`, and an **MCP tool ingress by outcome** panel on
`daari_mcp_tool_calls_total` so operators see flake / false-hit / budget /
MCP deny pressure without raw PromQL).

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

The same `soft_warnings` / `rejects` maps are also on `GET /v1/daari/stats` (and the
local web-ui) so operators can see cliff pressure without scraping Prometheus.
| `daari_ttft_preference_total{from,to}` | When `routing.ttft_aware` rewrites the heuristic local tier (e.g. L4→L3). Flat while TTFT bias is idle; rising means the preference path is active. Off / no-op picks do not increment. |
| `daari_rate_limit_degraded{mode}` | `1` while Redis rate-limit counting is degraded (`mode="sqlite_fallback"` or `mode="fail_open"`); clears to `0` when Redis answers again. Page when any pod stays at `1` — fleet RPM/TPM is no longer shared. |
| `daari_mcp_tool_calls_total{tool,outcome}` | MCP ingress `tools/call` (and legacy `/v1/mcp/query`) by tool name and `outcome` (`ok`, `deny`, `error`, `guardrail`). No-op when `observability.prometheus=false`. Rising `deny` vs `ok` is policy pressure on agent traffic. |
| `daari_team_budget_remaining_usd{team,window}` / `daari_team_budget_limit_usd{team,window}` / `daari_team_budget_remaining_hours{team,window}` | Per-team USD budget windows from the virtual-key team store (scrape-time snapshot). Flat when no teams have `max_usd` windows. Alert when remaining approaches zero before hard 402s. |
| `daari_team_rate_limit_remaining{team,kind,scope}` / `daari_team_rate_limit_limit{team,kind,scope}` | Per-team RPM/TPM remaining and ceilings (`scope="team"`, `kind="rpm"|"tpm"`). Flat when no teams have rpm/tpm set. |

Retries also appear per-request as `upstream_retry` trace steps with the status and
delay, so a slow request explains its own latency. See
[traces](traces-stats.md) and `upstream.*` in the
[config reference](../../reference/config.md).

## Next

→ [Config reference](../../reference/config.md)
