# daari

> **Open-source local execution router** — run cheaply on your machine, not in the cloud.

**Status:** Phase A complete · Phase A.1 setup shipped — [tracker](docs/TRACKING.md) · [plan](docs/plans/phase-a.md) · [PRD v0.4](docs/prd/PRD.md)

Route dev agent work through local tiers (cache → IDE tools → local AI) instead of frontier APIs. **Not a proxy** — a cost optimizer you own.

## Quick start (dev)

Full pickup guide (clone, venv, smoke test, pytest): **[docs/DEVELOPING.md](docs/DEVELOPING.md)**

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

## Docs

| Doc | Purpose |
|-----|---------|
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
