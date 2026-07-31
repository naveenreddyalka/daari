# Capacity and Helm

**Outcome:** Size a gateway-heavy fleet and install the chart.

## Sizing (rough)

| Resource | Guidance |
|----------|----------|
| Gateway replica | ~50–100 rps at ≥60% L0/L1 hit; ~5–15 rps if mostly L3 |
| Redis | ~200–400 MB / 100k cache entries |
| Postgres | ~1 KB/row ledger/traces; retain 30–90 days |
| HPA | CPU 70%, min 2 replicas; readiness `/ready` |

## Helm

Chart: `deploy/helm/daari/`. Point Redis/Postgres/org pool via values. Image: `ghcr.io/naveenreddyalka/daari`.

## Next

→ [Org cache](../features/org-cache.md)
