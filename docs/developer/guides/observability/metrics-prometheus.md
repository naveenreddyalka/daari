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

Import Grafana dashboard: `deploy/grafana/daari-dashboard.json`, or enable Helm
`grafanaDashboard.enabled` so the chart ships the same JSON as a labeled
ConfigMap (see [Capacity and Helm](../operations/capacity-helm.md#grafana-overview-dashboard)).
The dashboard includes a
**TTFT p50 / p95 by tier** panel on `daari_ttft_ms` for stream startup health,
a **Soft warnings by kind** panel on `daari_soft_warnings_total` for soft-band
pressure before hard 402/429, a **Hard rejects by kind** panel on
`daari_rejects_total` for cliffs after the soft band, a **Rate-limit Redis
degraded** panel on `daari_rate_limit_degraded` for shared-counter fallback,
a **TTFT preference by from→to** panel on `daari_ttft_preference_total`
for TTFT-aware local tier bias, a **Backend pool health & outstanding**
panel on `daari_backend_up` / `daari_backend_outstanding` (and request rate),
a **Concurrency gate** panel on `daari_rate_limit_in_flight` vs
`_in_flight_max` / `_queued`, a **Scoped in-flight by key/team/model** panel on
`daari_in_flight` / `daari_in_flight_max` (labels `scope` + `id`), alert-series panels for
`daari_upstream_retries_total`, `daari_cache_false_hits_avoided_total`, and
`daari_budget_alerts_total`, an **MCP tool ingress by outcome** panel on
`daari_mcp_tool_calls_total`, a **Tier shadow agree/disagree** panel on
`daari_tier_shadow_samples_total`, a **Compact-to-fit applied** panel on
`daari_compact_to_fit_applied_total`, a **Compact-to-fit tokens dropped** panel on
`daari_compact_to_fit_tokens_dropped_total`, an **MCP grant denied** panel on
`daari_mcp_grant_denied_total`, a **Decision classifier by outcome** panel on
`daari_decision_classifier_total` and a **Decision classifier latency p50 / p95**
panel on `daari_decision_classifier_latency_ms`, a **Virtual keys by status** panel on
`daari_virtual_keys{status}`, a **Retired model rejects** panel on
`daari_rejects_total{kind="retired"}`, a **Schema ok** stat on `daari_schema_ok`, a
**Systemone breaker events** panel on `daari_systemone_breaker_total`, a
**Virtual-model selection by mode** panel on `daari_virtual_model_selection_total`
(next to virtual-model failover pressure) for `ordered` vs `performance` picks,
`daari_virtual_model_slo_demotion_total{outcome}` for performance-mode latency-SLO
pressure (`demoted` when ≥1 over-SLO candidate ranks behind a within-SLO peer;
`within` when an SLO is configured and no demotion occurred — ratio companion;
no virtual-model name label because names are operator-defined and unbounded;
per-candidate `slo_demoted` stays on the inventory snapshot),
`daari_anthropic_message_thread_total{kind}` for Anthropic message-threads
create/continue pressure (`create` / `continue` successful Anthropic L6
passthrough; `continue_soft_ignored` when `anthropic.thread_continue_soft`
drops a continue on local/non-Anthropic; `continue_rejected` for fail-closed
400 — fixed four-kind enum, no message-id labels), an
**Admission priority by outcome** panel on `daari_admission_priority_total` for
`X-Daari-Priority` raise / lower / ignored / baseline traffic next to the concurrency
gate, **Service-tier not allowed rejects** / **Service-tier not allowed degraded**
panels on `daari_rejects_total{kind="service_tier_not_allowed"}` and
`daari_soft_warnings_total{kind="service_tier_not_allowed_degraded"}` for per-key/team
`allowed_service_tiers` allowlist pressure, and an
**Escalations & errors** panel on `daari_escalations_total` / `daari_errors_total` so
operators see flake / false-hit / budget / MCP deny / key-lifecycle / retired-model /
routing-shadow / compact-to-fit / schema-lag / judge-breaker / selection-mode /
SLO-demotion / admission-steer / service-tier-allowlist pressure without raw PromQL).

Useful series: request latency histograms by tier (`daari_request_latency_ms`),
stream time-to-first-token histograms by tier (`daari_ttft_ms` — stream path
only; non-stream omits TTFT), `daari_guardrail_trips_total`,
`daari_boundary_decisions_total`.

## Alert pack

The Helm chart ships an opt-in Prometheus Operator `PrometheusRule` pack
(`deploy/helm/daari/templates/prometheusrule.yaml`) gated on
`prometheusRules.enabled` (default **false**). Enable with scrape already
wired (`serviceMonitor.enabled=true` or an equivalent scrape of `/metrics`):

```bash
helm upgrade --install daari ./deploy/helm/daari \
  --set serviceMonitor.enabled=true \
  --set prometheusRules.enabled=true
```

Thresholds and `for` durations live under `prometheusRules.*` in
`deploy/helm/daari/values.yaml` (`backend`, `budget.fraction`,
`errors.rateThreshold`, `queue.threshold`, `guardrails.rateThreshold`,
`keys`, `cacheInvalidate.rateThreshold`). Each alert carries a `severity`
label and a `runbook_url` annotation pointing here.

| Alert | Metric(s) | Default trigger |
|-------|-----------|-----------------|
| `DaariBackendDown` | `daari_backend_up` | `== 0` for 5m |
| `DaariBudgetLow` | `daari_team_budget_remaining_usd` / `daari_team_budget_limit_usd` | remaining/limit &lt; 0.1 for 10m |
| `DaariErrorRateHigh` | `daari_errors_total{status}` | `sum(rate(...)) > 0.05` for 5m |
| `DaariAdmissionQueueDeep` | `daari_rate_limit_queued` | `> 10` for 5m |
| `DaariGuardrailTripSpike` | `daari_guardrail_trips_total` | `sum(rate(...)) > 1` for 5m |
| `DaariKeysExpiringSoon` | `daari_virtual_keys{status="expiring_soon"}` | `> 0` for 1h |
| `DaariCacheInvalidateErrors` | `daari_cache_invalidate_total{result="error"}` | `sum(rate(...)) > 0.05` for 5m |
| `DaariSchemaLagged` | `daari_schema_ok` | `== 0` for 5m |
| `DaariSystemoneBreakerSpike` | `daari_systemone_breaker_total{event=~"open|reject"}` | `sum(rate(...)) > 0.05` for 5m |

Requires the `monitoring.coreos.com` CRDs (kube-prometheus /
prometheus-operator), same as `ServiceMonitor`.

## Series worth watching

| Series | Reading it |
|--------|-----------|
| `daari_upstream_retries_total` | Transient upstream failures absorbed by backoff. Rising here while errors stay flat means clients never saw the instability. Rising alongside errors means the failures are not retryable — check for 401s or malformed requests. |
| `daari_cache_false_hits_avoided_total` | L1 hits vetoed by verification. Steady growth is the cache working; a spike suggests the similarity threshold is too loose. |
| `daari_cache_invalidate_total{scope,result}` | Admin `POST /v1/daari/cache/invalidate` (and daemon CLI via that path). `scope` is `model`\|`hash`\|`team`\|`key`\|`speed`\|`all`; `result` is `ok`\|`error`. Alert on surprise mass `rate(...[5m])` spikes. No per-hash labels. |
| `daari_cache_invalidate_entries_removed_total{layer}` | Entries removed by those ops (`layer="l0"` or `l1`). Bounded cardinality companion to the op counter. |
| `daari_soft_warnings_total{kind}` | Soft-band pressure before hard rejects: `kind="budget"` (`x-daari-budget-warning`), `kind="request_quota"` (`x-daari-quota-requests-warning`), scope-qualified rate-limit softs `kind="rate_limit_rpm"` \| `rate_limit_tpm` \| `rate_limit_rpd` \| `rate_limit_tpd` (`x-daari-ratelimit-warning`; attributed to the limiter dial that crossed soft, not a tighter concurrency gauge), `kind="fast_degraded_to_standard"` (Anthropic fast→standard), `kind="service_tier_degraded"` (OpenAI org/project `service_tier` restriction → retry without tier), `kind="service_tier_not_allowed_degraded"` (per-key/team `allowed_service_tiers` opt-in clear of a disallowed `service_tier`/`speed`; gateway event `service_tier_not_allowed` with `action=degrade`), `kind="thinking_between_tools_stripped"` (local tier dropped `thinking.type=between_tools`), or `kind="anthropic_sampling_stripped"` (L6 Anthropic hop under API version `2026-10-21` omitted `temperature`/`top_p`/`top_k`; gateway event `anthropic_sampling_stripped` lists the params). **Migration (#2096):** the rolled-up `kind="rate_limit"` soft counter is gone — sum `rate_limit_*` (or filter `kind=~"rate_limit_.*"`) for the former total. Rising here while 402/429 stay flat means agents are hovering in the soft band — scale Ollama or widen caps before hard rejects start. Hard 402/429 do not increment this counter. Overview Grafana charts all kinds under **Soft warnings by kind** and isolates USD soft pressure under **Soft USD budget warnings**. |
| `daari_rejects_total{kind}` | Hard denials only: `kind="budget"` (USD 402), `kind="request_quota"` (request-cap 402), `kind="budget_reservation"` (in-flight reservation 402 when `budgets.reserve_in_flight` is on), scope-qualified limiter 429s `kind="rate_limit_rpm"` \| `rate_limit_tpm` \| `rate_limit_rpd` \| `rate_limit_tpd`, in-flight `kind="concurrency"` (and scoped `key_concurrency` / `team_concurrency` / `model_concurrency`), `kind="retired"` (retired-model 410), or `kind="service_tier_not_allowed"` (per-key/team `allowed_service_tiers` hard 403). Soft warning headers never increment this. **Migration (#2096):** rolled-up `kind="rate_limit"` is gone for gateway/MCP limiter cliffs — sum `rate_limit_*` for the former total. Rising rejects after soft warnings means caps are undersized relative to demand. Overview Grafana isolates retired blocks under **Retired model rejects**; all kinds also chart under **Hard rejects by kind**. |
| `daari_budget_reservation_denied_total` | Admissions denied because settled plus in-flight reserved spend would exceed a USD window (`budgets.reserve_in_flight`). Also counted under `daari_rejects_total{kind="budget_reservation"}`. Flat when the flag is off. |
| `daari_virtual_keys{status}` | Scrape-time virtual-key lifecycle counts (`active`, `expired`, `expiring_soon`, `revoked`). Flat when no keys are stored. Rising `expired` / `expiring_soon` means credential rotation pressure. Stats counterpart: `virtual_keys` on `GET /v1/daari/stats`. Overview Grafana charts under **Virtual keys by status**. |
| `daari_ttft_preference_total{from,to}` | When `routing.ttft_aware` rewrites the heuristic local tier (e.g. L4→L3). Flat while TTFT bias is idle; rising means the preference path is active. Off / no-op picks do not increment. |
| `daari_admission_priority_total{outcome}` | Optional `X-Daari-Priority` admission resolution: `outcome="raised"` (successful boost above key/team ceiling), `lowered` (successful demotion), `ignored` (invalid header or disallowed raise when `allow_request_priority_boost` is false), or `baseline` (no header / header matches ceiling). No-header traffic increments `baseline`, never `raised`. Chart next to `daari_rate_limit_*` for queue-steer pressure. Overview Grafana: **Admission priority by outcome**. PromQL: `sum by (outcome) (rate(daari_admission_priority_total[5m]))`. |
| `daari_rate_limit_degraded{mode}` | `1` while Redis rate-limit counting is degraded (`mode="sqlite_fallback"` or `mode="fail_open"`); clears to `0` when Redis answers again. Page when any pod stays at `1` — fleet RPM/TPM is no longer shared. |
| `daari_budget_degraded{mode}` | `1` while Postgres usage-ledger spend reads failed and budget pre-checks soft-allow (`mode="soft_allow"`). Responses also carry `X-Daari-Budget-Degraded`. See [auth-and-keys](../configuration/auth-and-keys.md#postgres-outage-semantics-control-plane). |
| `daari_mcp_tool_calls_total{tool,outcome}` | MCP ingress `tools/call` (and legacy `/v1/mcp/query`) by tool name and `outcome` (`ok`, `deny`, `error`, `guardrail`). No-op when `observability.prometheus=false`. Rising `deny` vs `ok` is policy pressure on agent traffic. |
| `daari_team_budget_remaining_usd{team,window}` / `daari_team_budget_limit_usd{team,window}` / `daari_team_budget_remaining_hours{team,window}` | Per-team USD budget windows from the virtual-key team store (scrape-time snapshot). Flat when no teams have `max_usd` windows. Alert when remaining approaches zero before hard 402s. Overview Grafana charts remaining vs limit under **Team budget remaining (USD)**. |
| `daari_team_rate_limit_remaining{team,kind,scope}` / `daari_team_rate_limit_limit{team,kind,scope}` | Per-team RPM/TPM/RPD/TPD remaining and ceilings (`scope="team"`, `kind="rpm"|"tpm"|"rpd"|"tpd"`). Flat when no teams have rpm/tpm/rpd/tpd set. Overview Grafana charts remaining vs limit under **Team rate-limit remaining**. |
| `daari_key_rate_limit_remaining{key,kind}` / `daari_key_rate_limit_limit{key,kind}` | Per-key RPD/TPD remaining for keys with `rpd > 0` or `tpd > 0` (`kind="rpd"|"tpd"`). The `key` label is the key name (or key id if the name is empty), never the secret. A scrape does not consume the cap. Overview Grafana charts remaining vs limit under **Key rate-limit remaining**. |
| `daari_tier_shadow_samples_total{agreed}` | Local-tier answers replayed at a comparison tier (`agreed="true\|false"`). Rising `false` vs `true` means routing drift under `routing.shadow_sample_rate`. See [routing-tiers.md](../../concepts/routing-tiers.md) shadow section. Overview Grafana charts agree/disagree under **Tier shadow agree/disagree**. |
| `daari_cancelled_requests_total{phase}` | Client hung up (`phase` is `chat`, `anthropic`, `responses`, `stream`, `mcp`, `embed`, `asr`, `translation`, or `tts`) and the upstream call was cancelled. Normal completions do not increment. Overview Grafana charts by phase under **Cancelled requests by phase**. |
| `daari_request_deadline_exceeded_total` | Wall-clock request budget spent (`upstream.request_deadline_seconds` or `X-Daari-Deadline-Ms`) on chat, audio, embeddings, and MCP `tools/call` — not chat-only. Escalation stops without a frontier call. Overview Grafana charts under **Request deadline exceeded**. |
| `daari_compact_to_fit_applied_total` | Chat histories actually trimmed before L6 (`messages_before` != `messages_after`). Unchanged or fail-closed history does not increment. No-op when `observability.prometheus=false`. Overview Grafana charts under **Compact-to-fit applied**. |
| `daari_compact_to_fit_tokens_dropped_total` | Estimated tokens removed by compact-to-fit before L6 (`tokens_before - tokens_after` via the shared estimator). Increments only when a trim changes message count; unchanged or fail-closed history does not. Zero when unused. No-op when `observability.prometheus=false`. Stats counterpart: `compact_to_fit_tokens_dropped` on `GET /v1/daari/stats`. Overview Grafana charts under **Compact-to-fit tokens dropped**. |
| `daari_mcp_grant_denied_total` | MCP `initialize` / `tools/list` / `tools/call` (and legacy `/v1/mcp/query`) when `require_key_access_defined` fail-closed applies because the virtual key has no MCP grant. Ordinary tool-name `deny` does not increment. No-op when `observability.prometheus=false`. Overview Grafana charts under **MCP grant denied**. |
| `daari_agent_access_denied_total` | Responses `multi_agent.enabled` when `server.virtual_keys.agent_access_default_deny` fail-closed applies because the virtual key (and team) has no agent grant. Flag-off, master key, and granted keys do not increment. No-op when `observability.prometheus=false`. Stats counterpart: `agent_access_denied` on `GET /v1/daari/stats`. |
| `daari_decision_classifier_total{outcome}` | Optional `/v1/systemone` difficulty hop (`routing.decision_classifier.enabled`) by `outcome` (`success`, `heuristic_fallback`, `error`, `skipped`). `skipped` is enabled-but-bypassed (agent turn, tier override, empty text); disabled classifier does not increment. No-op when `observability.prometheus=false`. Overview Grafana charts under **Decision classifier by outcome**. |
| `daari_decision_classifier_latency_ms` | Histogram of classifier hop wall time (ms) for `success` / `heuristic_fallback` / `error` — not recorded on `skipped`. No-op when `observability.prometheus=false`. Overview Grafana charts p50/p95 under **Decision classifier latency p50 / p95**. |
| `daari_gzip_total{result,reason?}` / `daari_gzip_uncompressed_bytes_total` / `daari_gzip_compressed_bytes_total` | Buffered `application/json` gzip middleware (`Accept-Encoding: gzip`). `result="compressed"` or `result="skipped"` with low-cardinality `reason` (`below_min`\|`not_json`\|`already_encoded`\|`streaming`). Byte counters only on compressed responses. No path labels. Overview Grafana charts outcomes under **Gzip outcomes by result** and bytes under **Gzip bytes (uncompressed vs compressed)**. |
| `daari_cache_write_tokens_total{ttl}` | Provider prompt-cache write tokens by TTL class (`ttl="30m"\|"12h"\|"1h"\|"unset"`). Zero-token responses do not increment. Rising `12h` vs `30m` means invoice-true write premium pressure (OpenAI 2.5× / 1.25×). No-op when `observability.prometheus=false`. Overview Grafana charts under **Cache-write tokens by TTL**. |
| `daari_cost_input_usd_total` / `daari_cost_output_usd_total` | Process-lifetime input vs output USD (Kong AI Gateway 2.3.0 split: billable + cached-read + cache-write on input; same service-tier / region / Anthropic speed multipliers on both). The two sum to priced spend for identical requests; local/zero-cost paths add `0`/`0`. No per-model labels. Stats counterparts: `cost_input_usd` / `cost_output_usd` on `GET /v1/daari/stats`. Opt-in `observability.key_metrics` adds a bounded `key` (key_id) label on these counters and on `daari_requests_total` / `daari_tokens_total` (see below). |
| `daari_escalations_total` / `daari_errors_total{status}` | Local→frontier (L6) escalations and gateway/router errors. `status` is the HTTP status returned to the client (`503`, `500`, …); unlabeled call sites bucket as `status="0"`. Alert pack uses `sum(rate(daari_errors_total[…]))` so labeled series stay compatible. Stats counterpart: `errors_by_status` on `GET /v1/daari/stats`. Overview Grafana charts both under **Escalations & errors**. Opt-in `observability.team_metrics` adds a bounded `team` label on `daari_requests_total` / `daari_errors_total` (virtual-key teams store only; unknown/empty → `"-"`; off keeps exposition byte-identical). Latency histograms stay team-less as a deliberate cardinality bound. Live-editable via GET/PATCH `/v1/daari/config` ownership (no restart). |

## Grafana

**Virtual-model SLO demotion by outcome** charts
`sum by (outcome) (rate(daari_virtual_model_slo_demotion_total[5m]))` for
`demoted` / `within` pressure next to selection-by-mode (#2169).

Per-team traffic (requires `observability.team_metrics=true`):

```promql
sum by (team) (rate(daari_requests_total[5m]))
```

Per-key FinOps (requires `observability.key_metrics=true`; default off for
cardinality). Unauthenticated requests use `key="-"`; after
`observability.key_metrics_max_keys` (default 100) distinct key_ids, further
keys share `key="-overflow"`. Latency histograms stay key-less. Doctor emits an
optional tip when the flag is on.

```promql
sum by (key) (rate(daari_requests_total[5m]))
topk(10, sum by (key) (rate(daari_requests_total[5m])))
```

The same `soft_warnings` / `rejects` maps are also on `GET /v1/daari/stats` (and the
local web-ui) so operators can see cliff pressure without scraping Prometheus.
That stats payload also includes `backend_summary`
(`total` / `healthy` / `unhealthy` / `open_circuit`) next to the per-backend
rows — see [traces-stats.md](traces-stats.md).

Retries also appear per-request as `upstream_retry` trace steps with the status and
delay, so a slow request explains its own latency. See
[traces](traces-stats.md) and `upstream.*` in the
[config reference](../../reference/config.md).

## Next

→ [Config reference](../../reference/config.md)
