# daari — Task tracking

> Last updated: 2026-06-16  
> Update this file when phases/tasks complete.

## Legend

- [x] done  [ ] pending  [~] in progress  [-] deferred

---

## Phase A — Tracer bullet

| Task | Status | Notes |
|------|--------|-------|
| Scaffold (`pyproject.toml`, Typer CLI) | [x] | `cf50264` |
| Config (`Settings`, `~/.daari/config.yaml`) | [x] | |
| Internal model (`InternalRequest` / `InternalResponse`) | [x] | |
| L0 exact cache | [x] | diskcache |
| ProviderRegistry (cache + Ollama) | [x] | |
| OpenAI gateway (`POST /v1/chat/completions`) | [x] | |
| FastAPI server (`daari serve`) | [x] | port 11435 |
| Ollama executor (L3) | [x] | |
| Router L0 → L3 | [x] | |
| Metrics / `daari stats` | [x] | |
| Agent passthrough (tool_calls skip L0) | [x] | ADR-0004 |
| `X-Daari-No-Cache` / tier override headers | [x] | |
| Ollama-down → 503 | [x] | |
| Eval file GP-01–GP-10 | [x] | |
| Routing eval pytest | [x] | `6768fb8` |
| Live Ollama integration test (optional) | [x] | skipped without `OLLAMA_HOST` |
| Manual Cursor doc | [x] | [setup/cursor.md](setup/cursor.md) |
| Dev pickup docs | [x] | [DEVELOPING.md](DEVELOPING.md) |
| Streaming SSE | [-] | deferred per PRD |

**Exit criteria**

| Criterion | Status | Notes |
|-----------|--------|-------|
| Second identical prompt hits L0 | [x] | |
| `daari stats` shows tier breakdown | [x] | |
| Cursor via manual setup | [~] | doc ready; user smoke test deferred |
| GP-01–GP-10 pass MVP criteria | [x] | `tests/test_routing_eval.py` |

**Tests:** 24 pytest passing (`pytest` in project venv)

---

## Phase A.1 — Install & setup

| Task | Status | Notes |
|------|--------|-------|
| `scripts/install.sh` | [x] | venv + pip + Ollama pull; `13a2345` |
| `daari doctor` | [x] | `daari/setup/doctor.py` |
| `daari setup cursor --dry-run` | [x] | |
| `daari setup cursor` (apply + backup) | [x] | `aaf3f06` |
| `daari setup --undo cursor` | [x] | `daari/setup/backup.py` |
| Interactive `daari setup` wizard | [x] | `daari/setup/wizard.py` |
| `daari setup models` | [x] | `daari/setup/models.py` |
| JSONC patch helpers | [x] | `daari/setup/jsonc.py` |
| Setup tests | [x] | `tests/test_setup.py` |
| `daari install` (Typer) | [ ] | ROADMAP item — use `install.sh` today |
| L6 frontier executor | [ ] | not in tree |
| Confidence scoring → L6 | [ ] | per [routing-spec](prd/routing-spec.md) |

**Exit criteria**

| Criterion | Status | Notes |
|-----------|--------|-------|
| `./install.sh && daari doctor` passes | [~] | run on fresh clone to confirm |
| `daari setup cursor --dry-run` shows diff | [x] | covered by tests |
| Low-confidence response escalates to L6 | [ ] | needs executor + API keys |

**Key commits:** `13a2345` (scaffold), `aaf3f06` (apply, undo, wizard, models)

---

## Phase B (preview — not started)

Per [ROADMAP](prd/ROADMAP.md): L1 semantic cache, L2 rules, L2-dev, CCS, Lt CLI, PolicyEngine, L4 medium model, `daari setup openai-compat`, eval expansion GP-01–GP-20. L6 overlap with unfinished A.1 work.

---

## Deferred / user-owned

- Cursor smoke test on personal device (`daari setup cursor` + chat through daari)
- L6 frontier escalation (ADR-0001) — moved to Phase B entry or finish in A.1
- Streaming SSE for L3
- `daari install` Typer parity with `install.sh` (optional polish)

---

## How to update

1. Mark tasks `[x]` when merged to `main`; add commit hash in **Notes** when helpful.
2. Refresh **Last updated** and pytest count after test changes.
3. Do not mark done without implementation — check `daari/cli/`, `tests/`, and `git log`.
4. Keep Phase B+ as preview; detail stays in [ROADMAP](prd/ROADMAP.md) and [phase-a.md](plans/phase-a.md).
