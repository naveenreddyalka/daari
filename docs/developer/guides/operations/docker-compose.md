# Docker Compose

**Outcome:** Run daari + Ollama with one command.

## Steps

```bash
docker compose up
```

Profiles:

```bash
docker compose --profile org up              # org-cache :11436
docker compose --profile backends up -d      # Redis + Postgres
./scripts/smoke_backends.sh                  # SKIP if no Docker daemon
```

## Verify

`curl -fsS http://127.0.0.1:11435/ready`

## Next

→ [Capacity and Helm](capacity-helm.md) · [Install](../../get-started/install.md)
