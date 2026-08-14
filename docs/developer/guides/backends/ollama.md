# Ollama backend

**Outcome:** Local L3–L5 inference via Ollama.

## Steps

```bash
ollama pull llama3.2:3b
# optional L4
ollama pull llama3.1:8b
daari serve
daari doctor
```

Compose stack pulls models for you (`docker compose up`).

## Config

```yaml
ollama:
  base_url: http://127.0.0.1:11434
models:
  l3: llama3.2:3b
```

Add more hosts with `routing.local_pool` (issue #170). Empty `backends` keeps the single `ollama.base_url`. A dead host is skipped; `/ready` is `degraded` when some hosts are down and `not_ready` (503) when none can serve.

```yaml
routing:
  local_pool:
    strategy: least_outstanding   # or round_robin
    health_interval_seconds: 15
    backends:
      - id: gpu-a
        base_url: http://127.0.0.1:11434
        tiers: [L3, L4, L5]
      - id: gpu-b
        base_url: http://192.168.1.10:11434
        tiers: [L3, L4]
```

## Verify

`GET /ready` succeeds; chat completions return local tiers. `daari_meta.backend_id` names the host that served.

## Next

→ [MLX](mlx.md) · [Docker Compose](../operations/docker-compose.md)
