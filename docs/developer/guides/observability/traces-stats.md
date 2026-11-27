# Traces and stats

**Outcome:** Inspect per-request routing and daemon counters.

## Steps

```bash
daari stats
daari trace <trace_id>
curl -s http://127.0.0.1:11435/v1/daari/traces?limit=10 | python -m json.tool
```

`GET /v1/daari/events` lists newest-first gateway events when `observability.request_log.backend=postgres` (analyst/master or virtual-key read; JSONL-only returns **501**; `limit` default 100, max 1000; optional `team_id` / `key_id`).

Pass `X-Daari-Meta: true` on chat calls to embed `daari_meta` (tier, cache_hit, trace_id, boundary, `agent_turn`).

Web UI: `daari web-ui serve` → `http://127.0.0.1:11437`.

`GET /v1/daari/stats` also returns `backend_summary`
(`total` / `healthy` / `unhealthy` / `open_circuit`) derived from
`backends` so scripts can gauge pool pressure without counting rows.
The same payload includes `soft_warnings` and `rejects` kind maps (cliff
pressure before and after the soft band) — the Prometheus counterparts are
documented in [metrics-prometheus.md](metrics-prometheus.md).
`virtual_keys` mirrors scrape-time `daari_virtual_keys{status}` counts
(`active` / `expired` / `expiring_soon` / `revoked`; zeros when none stored).
`team_rate_limits` lists each team's `rpm`, `tpm`, and `rpd` remaining
(`team`, `kind`, `limit`, `remaining`); it is `[]` when no team has a ceiling.
`key_rate_limits` is the same shape for virtual keys with `rpd > 0` (`key` is the name, never the secret) and is `[]` otherwise.
Each `tiers.*` entry may include optional `p50_ms` / `p95_ms` from the
latency histogram (absent when that tier has no samples).
`compact_to_fit_applied` increments only when a compact-to-fit trim actually
changes the message count (unchanged or fail-closed history does not).
The same trim adds `tokens_before - tokens_after` (existing estimator) to
`compact_to_fit_tokens_dropped`; no-op and fail-closed paths leave it at 0.
Successful trims also set `daari_meta.compact_to_fit` (`messages_before` /
`messages_after`, plus `tokens_before` / `tokens_after`) when
`X-Daari-Meta: true`. The same fields are on the `compact_to_fit` trace
step (no step when the message count is unchanged).
`responses_truncation_auto` increments once per `/v1/responses` request whose
`truncation: "auto"` input was actually compacted to the serving-tier window;
the same compact adds `tokens_before - tokens_after` to
`responses_truncation_tokens_dropped` (and to the shared compact-to-fit
counters above). `responses_truncation_rejected` increments once per
OpenAI-shaped `context_length_exceeded` 400 (`truncation` omitted / `disabled`,
or `auto` that still cannot fit). Within-window and unknown-window requests
leave all three at 0. Prometheus counterparts are
`daari_responses_truncation_auto_total` /
`daari_responses_truncation_rejected_total` /
`daari_responses_truncation_tokens_dropped_total`.
`auto_caching_applied` increments once per Anthropic L6 hop where
`frontier.auto_caching` injected top-level `cache_control` because the client
sent none; `auto_caching_client_preserved` increments once per Anthropic L6 hop
where a caller-supplied top-level `cache_control` was forwarded verbatim
(client wins over the dial, counted whether the dial is on or off).
Non-Anthropic L6 hops and local tiers leave both at 0, as does dial-off with
no client value. Prometheus counterparts are
`daari_auto_caching_applied_total` / `daari_auto_caching_client_preserved_total`.
`mcp_grant_denied` increments once per `initialize`, `tools/list`, or
`tools/call` (JSON-RPC and legacy `/v1/mcp/query`) when
`integrations.mcp_policy.require_key_access_defined` fail-closed applies
because the virtual key has no MCP grant. Ordinary tool-name `deny`, granted
keys, master key, and flag-off installs do not increment it. The Prometheus
counterpart is `daari_mcp_grant_denied_total` (no-op when
`observability.prometheus=false`).
`agent_access_denied` increments once per Responses `multi_agent.enabled`
deny when `server.virtual_keys.agent_access_default_deny` fail-closed applies
because the virtual key (and team) has no agent grant. Flag-off, master key,
and granted keys do not increment it. The Prometheus counterpart is
`daari_agent_access_denied_total` (no-op when `observability.prometheus=false`).
`regional_processing_applied` and `regional_processing_uplift_usd` are
region → count / USD maps for the OpenAI regional-processing 1.10× surcharge:
a frontier request whose residency pin (`us` / `eu` / `au` / `in` / `jp` /
`ca` / `sg` / `kr` / `gb` / `ae`) and served model make
`regional_processing_factor` return 1.10 adds one to `applied[region]` and
`billed - billed / 1.10` to `uplift_usd[region]`. Unpinned requests,
pre-2026-03-05 OpenAI models, non-OpenAI models, and local tiers leave both
maps empty (`{}`); team-scoped stats zero them like the other fleet-wide
counters. Prometheus counterparts are
`daari_regional_processing_applied_total{region}` /
`daari_regional_processing_uplift_usd_total{region}`.
`frontier_binding` maps `"<source>:<outcome>"` → count for team/key BYOK
frontier bindings consumed at L6: `source` is `key` or `team` (whichever
layer supplied that binding side; key wins), `outcome` is `signed` (an L6
attempt signed with the bound credential), `pin_unmatched` (`frontier_pool`
names no configured slot → 502), or `unresolvable` (`secret://` ref failed
or resolved empty → 502). Global-key traffic never increments; the map is
empty until the first bound request. The Prometheus counterpart is
`daari_frontier_binding_total{source,outcome}`.

## Retention

Traces, the usage ledger, per-request spend rows, the audit log, shadow-check tables, MCP task
handles, batch jobs, and (when enabled) expired L0/L1 cache entries
grow without bound unless you set a window. Defaults are **0 days
(keep forever)** so an upgrade never deletes data.

```yaml
observability:
  retention:
    traces_days: 30
    ledger_days: 90
    spend_days: 90
    audit_days: 365
    shadow_days: 30
    tasks_days: 7
    batches_days: 30
    cache_prune: true   # reclaim L0/L1 entries past each cache's ttl_seconds
    request_log_days: 14
```

`daari serve` sweeps once a day in the background; failures are logged
(`retention.sweep_failed`) and never affect requests. `daari prune --dry-run`
prints per-store counts that would be deleted; `daari prune` applies the same
windows. When `audit_days > 0`, a prune writes a `retention.prune` audit row
summarizing what was removed (after the old rows are gone, so the summary stays).

Postgres (`observability.backend: postgres`) uses the same cutoffs on `traces`
and the ledger. `batches_days` also covers the postgres/memory batch backends.

## Verify

Complete a request; find its `trace_id` in meta and open it with `daari trace`.

## Next

→ [Savings report](savings-report.md) · [Prometheus](metrics-prometheus.md)
