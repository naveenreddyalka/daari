# Doctor and health probes

**Outcome:** Confirm daemon and backends are healthy.

## Steps

```bash
curl -fsS http://127.0.0.1:11435/health
curl -fsS http://127.0.0.1:11435/ready
daari doctor
daari doctor --suggest-models   # VRAM-aware stack advice
```

Orchestrators should use `/ready` (Ollama + cache handles), not only `/health`.

## Troubleshoot

| Probe | Failure meaning |
|-------|-----------------|
| `/health` | Process not listening |
| `/ready` | Dependency (Ollama/cache) not ready |
| doctor mlx/redis | Optional backend misconfigured |
| doctor `fleet_artifacts` | Optional: fleet signals (`DAARI_FLEET_REPLICAS` > 1, `cache.backend=redis`, or `observability.backend=postgres`) with sqlite `batches` / `files` / `responses` / ledger / `enterprise.audit_backend` — split-brain, 404, or incomplete audit-export risk |
| doctor `fleet_cache` | Optional: `DAARI_FLEET_REPLICAS` > 1 without `cache.backend=redis` — L0 / session pins / singleflight stay per-pod |
| doctor `budget_webhook_secret` | Optional: `alerts.budget_webhook_url` set without `alerts.budget_webhook_secret` — spoofable pages |
| doctor `helm_image_tag` | Optional: checkout `deploy/helm/daari/values.yaml` `image.tag` behind the running package version |

## Next

→ [Docker Compose](docker-compose.md)
