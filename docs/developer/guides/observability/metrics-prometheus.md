# Prometheus metrics

**Outcome:** Scrape `GET /metrics` for tier and boundary counters.

## Steps

Enable exposition (see config `observability` / prometheus flags in reference). Scrape:

```bash
curl -s http://127.0.0.1:11435/metrics | head
```

Import Grafana dashboard: `deploy/grafana/daari-dashboard.json`.

Useful series: request latency histograms by tier, `daari_guardrail_trips_total`, `daari_boundary_decisions_total`.

## Next

→ [Config reference](../../reference/config.md)
