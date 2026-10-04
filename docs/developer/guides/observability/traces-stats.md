# Traces and stats

**Outcome:** Inspect per-request routing and daemon counters.

## Steps

```bash
daari stats
daari trace <trace_id>
curl -s http://127.0.0.1:11435/v1/daari/traces?limit=10 | python -m json.tool
```

Pass `X-Daari-Meta: true` on chat calls to embed `daari_meta` (tier, cache_hit, trace_id, boundary, `agent_turn`).

Web UI: `daari web-ui serve` → `http://127.0.0.1:11437`.

`GET /v1/daari/stats` also returns `backend_summary`
(`total` / `healthy` / `unhealthy` / `open_circuit`) derived from
`backends` so scripts can gauge pool pressure without counting rows.
The same payload includes `soft_warnings` and `rejects` kind maps (cliff
pressure before and after the soft band) — the Prometheus counterparts are
documented in [metrics-prometheus.md](metrics-prometheus.md).
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
`X-Daari-Meta: true`.
`mcp_grant_denied` increments once per `initialize`, `tools/list`, or
`tools/call` (JSON-RPC and legacy `/v1/mcp/query`) when
`integrations.mcp_policy.require_key_access_defined` fail-closed applies
because the virtual key has no MCP grant. Ordinary tool-name `deny`, granted
keys, master key, and flag-off installs do not increment it. The Prometheus
counterpart is `daari_mcp_grant_denied_total` (no-op when
`observability.prometheus=false`).

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
