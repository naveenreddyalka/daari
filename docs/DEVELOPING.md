# Developing daari

> Pickup guide for cloning and running daari on a new machine (personal computer, CI, or handoff session).

## Prerequisites

| Tool | Version | Notes |
|------|---------|-------|
| **Python** | 3.12+ | `python3.12 --version` |
| **Ollama** | latest | [ollama.com](https://ollama.com) — local model runtime |
| **git** | any recent | clone the repo |

Optional: [Cursor](https://cursor.com) for IDE integration — run `daari setup cursor` or see [docs/setup/cursor.md](setup/cursor.md).

---

## Clone

```bash
git clone https://github.com/naveenreddyalka/daari
cd daari
```

---

## Install (manual)

```bash
python3.12 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
ollama pull llama3.2:3b
```

Or use the install script (Phase A.1):

```bash
./scripts/install.sh
```

---

## Run the daemon

```bash
source .venv/bin/activate
daari serve
```

Default endpoint: `http://127.0.0.1:11435/v1`

### Smoke test

```bash
curl http://127.0.0.1:11435/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"llama3.2:3b","messages":[{"role":"user","content":"Say hi"}]}'
```

Run the same curl again — the second response should include `"tier": "L0"` in `daari_meta` (cache hit).

```bash
daari stats   # tier breakdown from running daemon
```

---

## Health check

```bash
daari doctor
```

Checks Python version, config readability, Ollama reachability, default model presence, and optionally the running daemon.

---

## Tests

```bash
pytest
```

Routing evals (GP-01–GP-10) live in `tests/test_routing_eval.py`. Live Ollama integration tests are skipped unless `OLLAMA_HOST` is set.

---

## Cursor setup (optional)

Automated setup:

```bash
daari setup cursor --dry-run   # preview changes
daari setup cursor             # backup + patch Cursor config
daari setup --undo cursor      # restore latest backup
```

Or use the interactive wizard: `daari setup`

Manual fallback: **[docs/setup/cursor.md](setup/cursor.md)**

---

## What's implemented (Phase A)

| Component | Status |
|-----------|--------|
| FastAPI OpenAI-compat gateway (`POST /v1/chat/completions`) | ✅ |
| L0 exact cache (diskcache) | ✅ |
| L3 Ollama executor | ✅ |
| Router: L0 → L3, tool_calls passthrough | ✅ |
| `daari serve`, `daari stats` | ✅ |
| Config via `~/.daari/config.yaml` | ✅ |
| Routing evals GP-01–GP-10 | ✅ |
| Manual Cursor doc | ✅ |

**Verified commits:** `cf50264` (Phase A scaffold), `6768fb8` (routing evals).

---

## What's next (Phase A.1 checklist)

| Item | Status |
|------|--------|
| `scripts/install.sh` | ✅ |
| `daari doctor` | ✅ |
| `daari setup cursor --dry-run` | ✅ |
| `daari setup cursor` (apply + backup) | ✅ |
| `daari setup --undo cursor` | ✅ |
| `daari setup` interactive wizard | ✅ |
| `daari setup models` | ✅ |
| L6 frontier escalation (ADR-0001) | ⬜ deferred |

See [ROADMAP Phase A.1](prd/ROADMAP.md#phase-a1--install--frontier-fallback) and [setup-spec](prd/setup-spec.md).

---

## Config paths

| Path | Purpose |
|------|---------|
| `~/.daari/config.yaml` | User config (merged over package defaults) |
| `~/.daari/cache/l0` | L0 exact cache (diskcache) |
| `~/.daari/backups/<tool>/` | Setup recipe backups (Phase A.1+) |

Default config (from `daari/config/defaults.yaml`):

```yaml
server:
  host: 127.0.0.1
  port: 11435
models:
  l3: llama3.2:3b
ollama:
  base_url: http://127.0.0.1:11434
cache:
  l0:
    enabled: true
    path: ~/.daari/cache/l0
```

Environment overrides use prefix `DAARI_` with nested delimiter `__` (e.g. `DAARI_SERVER__PORT=11436`).

---

## Related docs

| Doc | Purpose |
|-----|---------|
| [CONTEXT.md](../CONTEXT.md) | Agent handoff — phase, decisions, next steps |
| [docs/plans/phase-a.md](plans/phase-a.md) | Phase A implementation plan |
| [docs/prd/PRD.md](prd/PRD.md) | Product requirements v0.4 |
| [docs/prd/ROADMAP.md](prd/ROADMAP.md) | Phase roadmap |
