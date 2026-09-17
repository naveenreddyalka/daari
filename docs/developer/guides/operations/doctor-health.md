# Doctor and health probes

**Outcome:** Confirm daemon and backends are healthy.

## Steps

```bash
curl -fsS http://127.0.0.1:11435/health   # {"status":"ok","version":"…"}
curl -fsS http://127.0.0.1:11435/ready
daari --version
daari doctor
daari doctor --suggest-models   # VRAM-aware stack advice
```

Orchestrators should use `/ready` (Ollama + cache handles), not only `/health`.
`/health` stays a liveness probe (`status=ok`) and now also reports the running
package `version` for upgrade/rollback discovery.

## Troubleshoot

| Probe | Failure meaning |
|-------|-----------------|
| `/health` | Process not listening |
| `/ready` | Dependency (Ollama/cache) not ready |
| doctor `redis` | Optional: when `cache.backend=redis`, PING `cache.redis_url` — timeout/unreachable means shared L0/rate-limit counters are dark |
| doctor `ready` | Optional: when the daemon answers, `GET /ready` — warn on `degraded` / `not_ready` (same signal as kube probes) |
| doctor `metrics_auth` | Optional: when the daemon answers, prometheus is on, and `server.api_key` is set — unauthenticated `GET /metrics` returning 401 means scrapers need Bearer / Helm `serviceMonitor.bearerTokenSecret` (or `observability.metrics_port`) |
| doctor mlx | Optional backend misconfigured |
| doctor `fleet_artifacts` | Optional: fleet signals (`DAARI_FLEET_REPLICAS` > 1, `cache.backend=redis`, or `observability.backend=postgres`) with sqlite `batches` / `files` / `responses` / ledger / `enterprise.audit_backend` — split-brain, 404, or incomplete audit-export risk |
| doctor `fleet_cache` | Optional: `DAARI_FLEET_REPLICAS` > 1 without `cache.backend=redis` — L0 / session pins / singleflight stay per-pod |
| doctor `soft_budget_ratio` | Optional: `frontier.soft_budget_ratio=0` while request quotas, USD budget windows, or `rate_limit` RPM/TPM are set — soft 402/429 warnings disabled |
| doctor `budget_webhook_secret` | Optional: `alerts.budget_webhook_url` set without `alerts.budget_webhook_secret` — spoofable pages |
| doctor `helm_image_tag` | Optional: checkout `deploy/helm/daari/values.yaml` `image.tag` behind the running package version |

## Next

→ [Docker Compose](docker-compose.md)
