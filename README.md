# daari

> **Local-first execution router** — cache, tools, and local models before frontier APIs.

**Status:** v1.3.0 — [docs site](https://naveenreddyalka.github.io/daari/) · [tracker](docs/TRACKING.md) · [release notes](docs/RELEASE-v1.3.0.md)

Route Cursor, Claude Code, and any OpenAI-compatible client through local tiers instead of paying frontier for repeat work. **Not a proxy** — a cost optimizer you run. Source-available under [PolyForm Noncommercial](LICENSE) (commercial use needs a license — [#227](https://github.com/naveenreddyalka/daari/issues/227)).

## Quick start

**pip:**

```bash
pip install daari
ollama pull llama3.2:3b
daari serve
```

**Docker (bundles Ollama):**

```bash
docker compose up
```

First start pulls the L3 model (~2 GB), then daari listens on `http://127.0.0.1:11435` (readiness: `GET /ready`). Prebuilt image: `ghcr.io/naveenreddyalka/daari`. Package: [pypi.org/project/daari](https://pypi.org/project/daari/).

**Docs** — **[Developer documentation](docs/developer/index.md)** (install, concepts, guides, reference). Contributors: [docs/DEVELOPING.md](docs/DEVELOPING.md).

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
- MCP server at `POST /mcp` (`initialize` / `tools/list` / `tools/call`), Sourcegraph/GHE/GitLab providers, org shared cache + collective learning (tracer), gateway API-key auth, MLX backend for Apple Silicon

## Docs

| Doc | Purpose |
|-----|---------|
| [`docs/developer/`](docs/developer/index.md) | **Start here** — get started, concepts, guides, reference, internals |
| [Docs site](https://naveenreddyalka.github.io/daari/) | Published MkDocs |
| [`docs/DEVELOPING.md`](docs/DEVELOPING.md) | Contributor pickup (clone, pytest, CI) |
| [`docs/prd/ROADMAP-v2.md`](docs/prd/ROADMAP-v2.md) | Forward roadmap |
| [`docs/TRACKING.md`](docs/TRACKING.md) | Living task tracker (maintainers) |
| [`docs/pitch/DEMO.md`](docs/pitch/DEMO.md) | Demo script |
| [`CONTEXT.md`](CONTEXT.md) | Agent handoff |

## Principles

- **Source-available** — free for personal, educational, and other noncommercial use
- **Local-first** — on-device by default
- **Cost-minimize** — cheapest capable path for every task
- **AI optional** — many tasks use IDE/CLI tools, not models

## License

Daari is licensed under the [PolyForm Noncommercial License 1.0.0](LICENSE):
personal, educational, research, and other noncommercial use is free. Use by or
for a business, or in any money-making activity, requires a commercial license —
contact naveenreddy.alka@gmail.com.

Required Notice: Copyright Naveen Reddy Alka (https://github.com/naveenreddyalka/daari)

Releases up to and including v1.2.0 were published under Apache 2.0 and remain
available under those terms.

## Repo

https://github.com/naveenreddyalka/daari
