# Traces and stats

**Outcome:** Inspect per-request routing and daemon counters.

## Steps

```bash
daari stats
daari trace <trace_id>
curl -s http://127.0.0.1:11435/v1/daari/traces?limit=10 | python -m json.tool
```

Pass `X-Daari-Meta: true` on chat calls to embed `daari_meta` (tier, cache_hit, trace_id, boundary).

Web UI: `daari web-ui serve` → `http://127.0.0.1:11437`.

## Retention

Traces, the usage ledger, the audit log, shadow-check tables, and MCP task
handles grow without bound unless you set a window. Defaults are **0 days
(keep forever)** so an upgrade never deletes data.

```yaml
observability:
  retention:
    traces_days: 30
    ledger_days: 90
    audit_days: 365
    shadow_days: 30
    tasks_days: 7
```

`daari serve` sweeps once a day in the background; failures are logged
(`retention.sweep_failed`) and never affect requests. `daari prune --dry-run`
prints per-store counts that would be deleted; `daari prune` applies the same
windows. When `audit_days > 0`, a prune writes a `retention.prune` audit row
summarizing what was removed (after the old rows are gone, so the summary stays).

Postgres (`observability.backend: postgres`) uses the same cutoffs on `traces`
and the ledger.

## Verify

Complete a request; find its `trace_id` in meta and open it with `daari trace`.

## Next

→ [Savings report](savings-report.md) · [Prometheus](metrics-prometheus.md)
