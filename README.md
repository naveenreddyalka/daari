# daari

> **Open-source local execution router** — run cheaply on your machine, not in the cloud.

**Status:** v1.1.2 Cursor BYOK E2E verified — [tracker](docs/TRACKING.md) · [validation](docs/VALIDATION.md) · [release notes](docs/RELEASE-v1.1.2-cursor-e2e.md)

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

## Feature snapshot (v1.1.0)

- Local-first routing chain with cache/rules/tooling/model tiers (`L0`, `L1`, `CCS`, `L2`, `Lt`, `L3-L6`)
- OpenAI-compatible and Anthropic-compatible gateways with SSE streaming support
- MCP ingress with `tools/list` + `tools/call`, schema-aware input validation, and structured errors
- C3 integration providers: Sourcegraph, GitHub Enterprise, and GitLab self-hosted trigger routing
- Enterprise E1/E2/E3 runtime: org mode, shared-cache service, learning feedback/profile APIs, CLI stats/export
- Local stats dashboard: `daari web-ui serve` (`packages/web-ui/`)
- Setup and health tooling: `daari setup ...`, `daari doctor`, `daari install`, demo + bench scripts

## Docs

| Doc | Purpose |
|-----|---------|
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | Repo layout, request flow, implementation map |
| [`docs/TRACKING.md`](docs/TRACKING.md) | Phase task tracker (A / A.1 / deferred) |
| [`docs/DEVELOPING.md`](docs/DEVELOPING.md) | Dev pickup — clone, run, test |
| [`docs/plans/phase-a.md`](docs/plans/phase-a.md) | Phase A implementation plan |
| [`docs/prd/PRD.md`](docs/prd/PRD.md) | Product requirements |
| [`docs/setup/cursor.md`](docs/setup/cursor.md) | Manual Cursor setup |
| [`CONTEXT.md`](CONTEXT.md) | Agent handoff |

## Principles

- **Open source** — Apache 2.0, you own the stack
- **Local-first** — on-device by default
- **Cost-minimize** — cheapest capable path for every task
- **AI optional** — many tasks use IDE/CLI tools, not models

## Repo

https://github.com/naveenreddyalka/daari
