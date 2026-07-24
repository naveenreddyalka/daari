# daari

> **Open-source local execution router** — run cheaply on your machine, not in the cloud.

**Status:** v1.2.0 Learning, Trust & Clients — [tracker](docs/TRACKING.md) · [validation](docs/VALIDATION.md) · [release notes](docs/RELEASE-v1.2.0.md)

Route dev agent work through local tiers (cache → IDE tools → local AI) instead of frontier APIs. **Not a proxy** — a cost optimizer you own.

## Quick start

Full pickup guide (clone, venv, smoke test, pytest): **[docs/DEVELOPING.md](docs/DEVELOPING.md)**

**One-click demo** (install, serve, smoke curl, stats):

```bash
./scripts/demo.sh
```

Manual steps:

```bash
python3.12 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
ollama pull llama3.2:3b
daari serve
```

```bash
curl http://127.0.0.1:11435/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"llama3.2:3b","messages":[{"role":"user","content":"Say hi"}]}'
```

Run the same curl twice — the second response should show `"tier": "L0"` in `daari_meta`.

## Feature snapshot (v1.2.0)

**Routing & caching**
- Local-first routing chain: `L0` exact cache → `L1` semantic cache (with draft injection) → `CCS`/`L2` rules → `Lt` CLI tools → `L3–L5` local models (Ollama or MLX) → `L6` frontier, with confidence-based escalation
- Cache trust you can measure: shadow-sampled **false-hit rate**, response-diversity monitoring, input normalization, per-category TTLs
- Prompt intelligence: category/complexity profiling, per-category policies, latency budgets, warm-model preference, learned routing from your own outcomes

**Learning (on-device)**
- Implicit outcome capture + explicit accept/reject feedback → `daari learn stats/recommend`
- Auto-tuned per-category confidence thresholds, opt-in example capture → `daari learn finetune` (MLX LoRA) → `daari learn deploy`
- Opt-in, review-first anonymized stats export (`daari learn export-stats`) — metadata only, never prompts

**Clients (one-click)**
- Cursor (BYOK via tunnel + API-key auth), Claude Code (full tool passthrough), JetBrains AI Assistant (Ollama-compatible facade), VS Code, any OpenAI/Anthropic SDK
- Per-project profiles (`.daari.yaml`): tier caps, no-frontier, latency budgets per repo

**Observability & spend**
- Per-request traces (`daari trace`), usage ledger with estimated savings (`daari report`, Markdown export), web dashboard (`daari web-ui serve`)
- Monthly/daily frontier budgets with soft warnings, per-client cost attribution, optional pre-frontier PII scrub

**Platform**
- MCP ingress (`tools/list`/`tools/call`), Sourcegraph/GHE/GitLab providers, org shared cache + collective learning (tracer), gateway API-key auth, MLX backend for Apple Silicon

## Docs

| Doc | Purpose |
|-----|---------|
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | Repo layout, request flow, implementation map |
| [`docs/TRACKING.md`](docs/TRACKING.md) | Living phase/task tracker |
| [`docs/DEVELOPING.md`](docs/DEVELOPING.md) | Dev pickup — clone, run, test |
| [`docs/prd/PRD.md`](docs/prd/PRD.md) | Product requirements |
| [`docs/prd/ROADMAP-v2.md`](docs/prd/ROADMAP-v2.md) | Forward roadmap: OSS launch, gateway parity, enterprise scale |
| [`docs/setup/cursor.md`](docs/setup/cursor.md) | Cursor setup (tunnel + auth) |
| [`docs/setup/claude-code.md`](docs/setup/claude-code.md) | Claude Code one-click setup |
| [`CONTEXT.md`](CONTEXT.md) | Agent handoff |

## Principles

- **Open source** — Apache 2.0, you own the stack
- **Local-first** — on-device by default
- **Cost-minimize** — cheapest capable path for every task
- **AI optional** — many tasks use IDE/CLI tools, not models

## Repo

https://github.com/naveenreddyalka/daari
