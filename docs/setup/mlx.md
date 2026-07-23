# MLX backend (Apple Silicon)

daari can serve any local tier (L3/L4/L5) through
[mlx-lm](https://github.com/ml-explore/mlx-lm) instead of Ollama
(issue #97, roadmap Phase C2). On M-series Macs MLX typically delivers higher
tokens/sec, and it reuses the `mlx-community/*` models already used by the
`daari learn finetune` pipeline.

## Setup

1. Install mlx-lm (same optional dependency as fine-tuning):

```bash
pip install mlx-lm
```

2. Start the server (downloads the model on first run):

```bash
mlx_lm.server --model mlx-community/Llama-3.2-3B-Instruct-4bit --port 11440
```

3. Map tiers in `~/.daari/config.yaml`:

```yaml
mlx:
  enabled: true
  base_url: http://127.0.0.1:11440
  models:
    L3: mlx-community/Llama-3.2-3B-Instruct-4bit
    # L4: mlx-community/Meta-Llama-3.1-8B-Instruct-4bit
```

4. Restart the daemon and verify:

```bash
launchctl kickstart -k gui/$(id -u)/com.daari.serve
daari doctor        # shows an "mlx" check when enabled
```

## Behavior

- Only tiers listed under `mlx.models` route to MLX; everything else stays on
  Ollama. Mixed setups (L3 on MLX, L4/L5 on Ollama) are fine.
- All router semantics are unchanged: caching, escalation, tier caps, latency
  budgets, traces, and the usage ledger all work identically. Responses report
  `executor: mlx` and `provider_id: mlx:l3` in `daari_meta`.
- Embeddings (L1 semantic cache) still come from Ollama — keep it running.
- Streaming works through both the OpenAI and Anthropic gateways; MLX's SSE
  chunks are converted to the internal event shape transparently.

## Notes

- `mlx_lm.server` binds to localhost by default; it has no auth, so do not
  expose its port through a tunnel — only daari's gateway should be public.
- Warm-model preference and `daari profile` benchmarks currently cover Ollama
  models only.
