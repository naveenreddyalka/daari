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

## Verify

`GET /ready` succeeds; chat completions return local tiers.

## Next

→ [MLX](mlx.md) · [Docker Compose](../operations/docker-compose.md)
