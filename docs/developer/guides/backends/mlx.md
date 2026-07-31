# MLX backend (Apple Silicon)

**Outcome:** Serve L3–L5 via `mlx_lm.server`.

## Steps

```bash
pip install mlx-lm
mlx_lm.server --model mlx-community/Llama-3.2-3B-Instruct-4bit --port 11440
```

```yaml
mlx:
  enabled: true
  base_url: http://127.0.0.1:11440
  models:
    L3: mlx-community/Llama-3.2-3B-Instruct-4bit
```

Restart daari; `daari doctor` shows an mlx check.

## Verify

Chat with `X-Daari-Meta: true` — executor should reflect MLX when selected.

## Next

→ [Learning loop](../../concepts/learning-loop.md)
