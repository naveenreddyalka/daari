# Capacity and Helm

**Outcome:** Size a gateway-heavy fleet and install the chart.

## Sizing (rough)

| Resource | Guidance |
|----------|----------|
| Gateway replica | Measured on an M4 Pro: see [benchmark-load.md](../../resources/benchmark-load.md). Older estimate (~50–100 rps cache-heavy, ~5–15 rps L3-heavy) is superseded by that page. |
| Redis | ~200–400 MB / 100k cache entries |
| Postgres | ~1 KB/row ledger/traces; retain 30–90 days |
| HPA | CPU 70%, min 2 replicas; readiness `/ready` |

## Helm

Chart: `deploy/helm/daari/`. Point Redis/Postgres/org pool via values. Image: `ghcr.io/naveenreddyalka/daari`.

Moving an installed release to a new image tag (`helm upgrade --atomic`, rollback,
what survives in Redis/Postgres): [Upgrade and config migration](upgrade.md).

## Next

→ [Org cache](../features/org-cache.md) · [Upgrade and config migration](upgrade.md)
