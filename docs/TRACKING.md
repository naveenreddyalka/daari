# daari — implementation tracking

> Living checklist for phase delivery. Update when tasks land or exit criteria change.  
> **Last updated:** 2026-06-16  
> **Tests:** 24 pytest passing (`pytest` in project venv)

**Plans:** [Phase A](plans/phase-a.md) · [ROADMAP Phase A.1+](prd/ROADMAP.md) · [PRD](prd/PRD.md)

---

## Phase A — Tracer bullet (L0 + L3 + OpenAI gateway)

**Status:** Complete (exit criteria met)

| # | Task | Status |
|---|------|--------|
| A1 | Scaffold — `pyproject.toml`, Typer CLI | [x] `cf50264` |
| A2 | Config — `Settings` / `~/.daari/config.yaml` | [x] |
| A3 | Internal model — `InternalRequest` / `InternalResponse` | [x] |
| A4 | L0 exact cache | [x] |
| A5 | ProviderRegistry — cache + Ollama | [x] |
| A6 | OpenAI gateway — `POST /v1/chat/completions` | [x] |
| A7 | FastAPI server — `daari serve` | [x] |
| A8 | Ollama executor (L3) | [x] |
| A9 | Router — L0 → L3 | [x] |
| A10 | Metrics / tier counters | [x] |
| A11 | `daari stats` | [x] |
| A12 | Agent passthrough (tool_calls skip L0) | [x] |
| A13 | `X-Daari-No-Cache`, tier override headers | [x] |
| A14 | Ollama-down → clear 503 | [x] |
| A15 | Eval file GP-01–GP-10 | [x] |
| A16 | Routing eval pytest | [x] `6768fb8` |
| A17 | Live Ollama integration (optional skip) | [x] |
| A18 | Manual Cursor doc | [x] [setup/cursor.md](setup/cursor.md) |
| A19 | Dev pickup docs | [x] [DEVELOPING.md](DEVELOPING.md) |
| A20 | Streaming SSE | [ ] Deferred (documented in PRD) |

### Phase A exit criteria

- [x] Second identical prompt hits **L0**
- [x] `daari stats` shows tier breakdown
- [~] Cursor via manual setup — **smoke test on a machine with Cursor installed** (non-blocking)
- [x] GP-01–GP-10 eval prompts pass (`tests/test_routing_eval.py`)

---

## Phase A.1 — Install & setup (+ frontier fallback per ROADMAP)

**Status:** In progress — setup stack shipped; L6 / `daari install` not started

**Merged commits (main):**

| Commit | What |
|--------|------|
| `13a2345` | `install.sh`, `daari doctor`, Cursor recipe scaffold (dry-run), DEVELOPING handoff |
| `aaf3f06` | Cursor **apply** + **backup/undo**, interactive **`daari setup`** wizard, **`daari setup models`**, `tests/test_setup.py` |

### Ships (ROADMAP)

| Component | Status | Notes |
|-----------|--------|-------|
| `./scripts/install.sh` | [x] | bash venv + pip + Ollama pull |
| `daari install` (Typer) | [ ] | ROADMAP item — use script today |
| `daari doctor` | [x] | `daari/setup/doctor.py` |
| `daari setup cursor` | [x] | apply + `--dry-run` + `--force` |
| `daari setup --undo cursor` | [x] | backup restore via `daari/setup/backup.py` |
| Interactive `daari setup` | [x] | `daari/setup/wizard.py` |
| `daari setup models` | [x] | `daari/setup/models.py` |
| JSONC patch helpers | [x] | `daari/setup/jsonc.py` |
| L6 frontier executor | [ ] | Phase A.1 ROADMAP — not in tree |
| Confidence scoring → L6 | [ ] | Per [routing-spec](prd/routing-spec.md) |

### Phase A.1 exit criteria (ROADMAP)

- [~] `./install.sh && daari doctor` passes — **automated in CI/dev; run on fresh clone to confirm**
- [x] `daari setup cursor --dry-run` shows planned diff (covered by `tests/test_setup.py`)
- [ ] Low-confidence local response escalates to **L6** (requires keys + executor)

### Remaining before calling A.1 “done”

1. **L6 escalation** + confidence scoring (ADR-0001)
2. **`daari install`** Typer parity with `install.sh` (optional polish)
3. **Cursor smoke test** on hardware with Cursor — [cursor.md](setup/cursor.md)
4. Re-run **`./install.sh && daari doctor`** on a clean machine and check off exit criterion

---

## Phase B+ — Preview (deferred)

Per [ROADMAP](prd/ROADMAP.md): L1 semantic cache, L2 rules, L2-dev, CCS, Lt CLI, PolicyEngine, multi-model, `daari setup openai-compat`, Anthropic gateway (Phase C), MCP, etc.

**Next engineering focus:** Phase B.0 cache/rules/Lt CLI stack; Phase B frontier items overlap with unfinished A.1 L6 work.

---

## Test inventory

| Suite | File | Count (approx.) |
|-------|------|-----------------|
| L0 / router / gateway | `test_*.py` (excl. setup, doctor, eval) | — |
| Routing evals GP-01–GP-10 | `test_routing_eval.py` | — |
| Doctor | `test_doctor.py` | — |
| Setup (cursor, undo, wizard, models) | `test_setup.py` | — |
| **Total** | | **24 passed** (2026-06-16) |

---

## How to update this file

1. Mark tasks `[x]` when merged to `main` with a commit hash in the table if helpful.
2. Refresh **Last updated** and pytest count after meaningful test changes.
3. Keep Phase B+ as preview only — detail lives in ROADMAP / phase plans.
