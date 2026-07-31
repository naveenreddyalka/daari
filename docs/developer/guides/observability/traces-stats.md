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

## Verify

Complete a request; find its `trace_id` in meta and open it with `daari trace`.

## Next

→ [Savings report](savings-report.md) · [Prometheus](metrics-prometheus.md)
