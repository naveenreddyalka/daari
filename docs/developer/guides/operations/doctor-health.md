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

## Next

→ [Docker Compose](docker-compose.md)
