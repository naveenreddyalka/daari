# Capacity and Helm

**Outcome:** Size a gateway-heavy fleet and install the chart.

## Sizing (rough)

| Resource | Guidance |
|----------|----------|
| Gateway replica | Measured on an M4 Pro: see [benchmark-load.md](../../resources/benchmark-load.md). Older estimate (~50–100 rps cache-heavy, ~5–15 rps L3-heavy) is superseded by that page. |
| Redis | ~200–400 MB / 100k cache entries |
| Postgres | ~1 KB/row ledger/traces; retain 30–90 days |
| HPA | CPU 70%; optional KEDA request-rate scaler is off until you enable it |

Redis is an accelerator, not a single point of failure: set `cache.backend: redis` for shared L0/L1 and fleet-wide RPM/TPM counters, but expect a Redis outage to degrade rate limiting to per-replica SQLite (or `rate_limit.fail_open`) and mark `/ready` as `degraded` with HTTP 200 while the gateway keeps serving. Tune `cache.redis_timeout_seconds` (default 2s). Details: [Auth and keys](../configuration/auth-and-keys.md#redis-outage-semantics-fleet).

## Helm

Chart: `deploy/helm/daari/`. Point Redis/Postgres/org pool via values. Image: `ghcr.io/naveenreddyalka/daari`.

Defaults are a **single replica** (`replicaCount: 1`, `autoscaling.minReplicas: 1`) with `postgres.enabled: false`. Batches, files, responses, the usage ledger, and the audit log then use per-pod SQLite — fine for one pod. Raising replicas (or HPA min) above 1 without Postgres splits those stores across pods (404s / divergent counters / incomplete `daari audit export`). `helm install` NOTES and `daari doctor` (via `DAARI_FLEET_REPLICAS`) warn on that combination.

For a multi-replica fleet, enable the chart Postgres helper (sets observability / batches / files / responses / audit backends):

```yaml
replicaCount: 2
autoscaling:
  minReplicas: 2
postgres:
  enabled: true
  url: postgresql://daari:daari@postgres:5432/daari
```

Moving an installed release to a new image tag (`helm upgrade --atomic`, rollback,
what survives in Redis/Postgres): [Upgrade and config migration](upgrade.md).

### Request-rate autoscaling (KEDA)

CPU HPA misses cache-heavy replicas that stay idle while `daari_requests_total`
climbs. `autoscaling.keda` is **off** by default and renders nothing — no
ScaledObject, no CRDs. The chart does not install KEDA. On a cluster that
already has KEDA and Prometheus:

```yaml
autoscaling:
  enabled: true          # CPU HPA still renders
  keda:
    enabled: true
    serverAddress: http://prometheus-operated.monitoring.svc:9090
    query: sum(rate(daari_requests_total[1m]))
    threshold: "50"      # desired replicas ≈ query / threshold
    minReplicaCount: 1   # refused above 1 until postgres.enabled
    maxReplicaCount: 10
```

`minReplicaCount` above 1 with `postgres.enabled: false` fails `helm template`
(per-pod SQLite). NOTES still warn when the effective replica floor is above 1
without Postgres. KEDA also creates its own HPA; leave `autoscaling.enabled`
on if you still want the chart's CPU HPA beside it.

### Bumping `image.tag` / `appVersion`

After a tagged release (e.g. `v1.4.0`), update **both** in the same change — do **not** create git tags from routine chart PRs:

1. `deploy/helm/daari/Chart.yaml` → `appVersion: "X.Y.Z"`
2. `deploy/helm/daari/values.yaml` → `image.tag: "X.Y.Z"`

Keep them equal to `pyproject.toml` / `daari.__version__`. `tests/unit/test_helm_chart.py` fails if they drift.

### Graceful rollouts / drains

Defaults leave interactive SSE streams (chat, Responses, MCP) and in-flight
batch drains a window to finish before kubelet SIGTERMs the pod:

| Value | Default | Role |
|-------|---------|------|
| `terminationGracePeriodSeconds` | `60` | Total time after SIGTERM before SIGKILL. Size above the longest stream you expect (and `sse_keepalive_seconds`). |
| `lifecycle.preStopSleepSeconds` | `5` | `preStop` sleep so Service endpoint removal propagates before SIGTERM. Set `0` to omit the lifecycle block. |
| `strategy.rollingUpdate` | `maxUnavailable: 0` / `maxSurge: 1` | Never drop capacity during upgrades. |

### Pod security and disruption budget

Defaults harden the pod (`runAsNonRoot` uid `1000`, drop all capabilities,
`readOnlyRootFilesystem`) and mount emptyDirs at `/home/daari/.daari` and
`/tmp` so the gateway can still write local state under a read-only root.
Swap the `daari-home` emptyDir for a PVC when you need durable per-pod SQLite
across restarts.

`podDisruptionBudget` defaults to **disabled**. For multi-replica fleets
(alongside HPA / `replicaCount` ≥ 2 and Postgres), enable it so voluntary
node drains keep interactive SSE alive:

```yaml
replicaCount: 2
autoscaling:
  minReplicas: 2
podDisruptionBudget:
  enabled: true
  minAvailable: 1
```

Use `maxUnavailable: 1` instead of `minAvailable` when you have a single
replica and still want a PDB (minAvailable=1 blocks draining the only pod).
PDB and HPA compose: HPA sets desired replicas; the PDB only constrains
voluntary evictions during drains/upgrades.

### Prometheus ServiceMonitor

`serviceMonitor` defaults to **disabled**. On clusters with the Prometheus
Operator (`monitoring.coreos.com` CRDs), enable it so kube-prometheus scrapes
`GET /metrics`. Chart defaults already set `DAARI_OBSERVABILITY__PROMETHEUS=true`.
Add `serviceMonitor.labels` when your operator selects monitors by release label.

**Scrape path (pick one):**

| Mode | Values | ServiceMonitor target | Auth |
|------|--------|----------------------|------|
| API port (default) | `observability.metricsPort: 0` | Service port `http` | Bearer via `serviceMonitor.bearerTokenSecret` when `server.api_key` protects `/metrics` |
| Private metrics port | `observability.metricsPort: 9090` (example) | Service port `metrics` | None — scrape-only listener; keep off public ingress |

```yaml
# Private scrape listener (no Bearer on /metrics):
observability:
  metricsPort: 9090
serviceMonitor:
  enabled: true
  labels:
    release: kube-prometheus-stack
```

```yaml
# API-port scrape with Bearer (metricsPort left at 0):
# kubectl create secret generic daari-metrics-token \
#   --from-literal=token="$DAARI_SERVER__API_KEY"
serviceMonitor:
  enabled: true
  bearerTokenSecret:
    name: daari-metrics-token
    key: token
```

When `metricsPort > 0`, the chart sets `DAARI_OBSERVABILITY__METRICS_PORT`,
adds a `metrics` containerPort / Service port, and points ServiceMonitor at
`metrics` (bearer settings are ignored for that endpoint).

See [Prometheus metrics](../observability/metrics-prometheus.md).

### Org GPU pool

`orgPool` defaults to **disabled**. When enabled, the Deployment sets
`DAARI_ROUTING__ORG_POOL__ENABLED` and `DAARI_ROUTING__ORG_POOL__BASE_URL` so
local tiers can fall through to a shared Ollama/vLLM pool before frontier.
`helm install` NOTES echo the same when `orgPool.enabled=true` (including
`baseUrl`). When `serviceMonitor.enabled=true`, NOTES also remind operators that
Prometheus scrapes Service `/metrics` and that `bearerTokenSecret` is needed if
the API key protects metrics on the API port.

```yaml
orgPool:
  enabled: true
  baseUrl: http://gpu-pool.internal:11434
```

### Embedder base URL

`ollama.baseUrl` defaults to empty, so the image keeps its localhost Ollama
default and the chart does not set `DAARI_OLLAMA__BASE_URL`. Set it when the
embedder should leave the pod — `POST /v1/embeddings` and L1 both use
`settings.ollama.base_url`. This is separate from `orgPool`, which only sets
`DAARI_ROUTING__ORG_POOL__BASE_URL` for chat routing.

```yaml
ollama:
  baseUrl: http://ollama.internal:11434
```

## Next

→ [Org cache](../features/org-cache.md) · [Upgrade and config migration](upgrade.md) · [Batches](../features/batches.md)
