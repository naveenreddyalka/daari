# daari — Task tracking

> Last updated: 2026-06-20  
> Update this file when phases/tasks complete.  
> Repo layout and request flow: [ARCHITECTURE.md](ARCHITECTURE.md)

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
| Streaming SSE | [x] | basic OpenAI-style SSE passthrough for stream=true |

**Exit criteria**

| Criterion | Status | Notes |
|-----------|--------|-------|
| Second identical prompt hits L0 | [x] | |
| `daari stats` shows tier breakdown | [x] | |
| Cursor via manual setup | [~] | doc ready; user smoke test deferred |
| GP-01–GP-10 pass MVP criteria | [x] | `tests/test_routing_eval.py` |

**Tests:** see [Testing](#testing) below.

---

## Testing

| Layer | Location | CI | Notes |
|-------|----------|-----|-------|
| **Unit** | `tests/unit/` | ✅ | cache keys, semantic similarity, metrics, settings, internal models, confidence, L6 escalation |
| **Integration (mocked)** | `tests/integration/test_gateway_flow.py`, `tests/integration/test_l1_semantic_cache.py`, `tests/integration/test_l6_escalation.py`, `tests/test_phase_a.py`, `tests/test_routing_eval.py` | ✅ | gateway + router + L0/L1 cache + L6; Ollama mocked |
| **Integration (live Ollama)** | `tests/integration/test_ollama_live.py` | skipped | `@pytest.mark.integration`; run with `OLLAMA_HOST=http://127.0.0.1:11434 pytest -m integration` |
| **Benchmark** | `tests/benchmark/` | skipped | `@pytest.mark.benchmark`; L0 vs L3 latency |
| **Setup / doctor** | `tests/test_setup.py`, `tests/test_doctor.py` | ✅ | dry-run, backup, doctor checks |

**Commands**

```bash
pytest                              # default: unit + mocked integration (no live Ollama)
pytest -m "not integration and not benchmark"   # same as CI
pytest -m integration               # live Ollama only (needs OLLAMA_HOST + model pulled)
pytest -m benchmark                 # optional latency checks
./scripts/demo.sh                   # one-click smoke (serve + curl + stats)
```

**CI:** `.github/workflows/ci.yml` — Python 3.12, `pytest -m "not integration and not benchmark"` on push/PR. No secrets.

**Gaps (planned):** L6 live API integration test (optional, requires frontier key/model); richer streaming metadata.

**Count:** 70 passed (`OLLAMA_HOST=http://127.0.0.1:11434 pytest -v`)

---

## Phase A.1 — Install & setup

| Task | Status | Notes |
|------|--------|-------|
| `scripts/install.sh` | [x] | venv + pip + Ollama pull; `13a2345` |
| `daari doctor` | [x] | `daari/setup/doctor.py` |
| `daari setup cursor --dry-run` | [x] | |
| `daari setup cursor` (apply + backup) | [x] | `aaf3f06` |
| `daari setup --undo cursor` | [x] | `daari/setup/backup.py` |
| Interactive `daari setup` wizard | [x] | `daari/setup/wizard.py` — **partial vs spec** (see gaps below) |
| `daari setup models` | [x] | `daari/setup/models.py` |
| JSONC patch helpers | [x] | `daari/setup/jsonc.py` |
| Setup tests | [x] | `tests/test_setup.py` |
| `daari install` (Typer) | [x] | wrapper command to `scripts/install.sh` with `--run-doctor` |
| L6 frontier executor | [x] | `daari/router/frontier.py` — OpenAI-compat httpx |
| Confidence scoring → L6 | [x] | `daari/router/confidence.py` — binary heuristic per routing-spec |

**Exit criteria**

| Criterion | Status | Notes |
|-----------|--------|-------|
| `./install.sh && daari doctor` passes | [~] | run on fresh clone to confirm |
| `daari setup cursor --dry-run` shows diff | [x] | covered by tests |
| Low-confidence response escalates to L6 | [x] | when `frontier.enabled` + API key present |

**Wizard gaps (A.1 spec vs shipped):** single-choice menu (not multi-select); frontier helper writes hints/templates only (no secret capture by design); IntelliJ/Claude deferred to Phase B per setup-spec.

**Key commits:** `13a2345` (scaffold), `aaf3f06` (apply, undo, wizard, models)

---

## Phase B — Full local-first stack

| Task | Status | Notes |
|------|--------|-------|
| L1 semantic cache | [x] | Ollama embeddings + diskcache; router L0 → L1 → L3 |
| L2 rules engine | [x] | JSON/YAML deterministic transforms before model tiers |
| L2-dev developer commands | [x] | regex rules for git/test/lint + readonly command-context prompts |
| CCS command context store | [x] | disk-backed command output reuse with TTL |
| PolicyEngine B.0 | [x] | allow/block + unknown deny/ask outcomes for Lt execution |
| Lt B.0 CLI tools | [x] | `git status`, `git diff`, `pytest`, `eslint` command dispatch |
| L4 medium model | [x] | second local model tier + L3→L4→L6 escalation path |
| `daari setup openai-compat` | [x] | prints OPENAI_* exports + writes `~/.daari/.env.example` |
| Wizard frontier key helper | [x] | optional profile hint + env template (no config secret storage) |
| `daari context clear` | [x] | clears L0/L1/CCS caches |
| Doctor L4 pull hint | [x] | optional `model_l4` hint with pull command |
| Eval expansion GP-11–GP-20 | [x] | prompts + regression assertions updated |

**Exit criteria (Phase B — partial)**

| Criterion | Status | Notes |
|-----------|--------|-------|
| Paraphrased prompt hits L1 | [x] | mocked embedder tests |
| L1 metrics in `daari stats` | [x] | tier counter `L1` |
| L0 → CCS → L1 → L2-dev → L2 → Lt → L3/L4 routing order | [x] | with tool_calls bypass caches retained |

**Tests:** see [Testing](#testing) below.

---

## Deferred / user-owned

- Cursor smoke test on personal device (`daari setup cursor` + chat through daari)
- L4 model pull/install still user-managed (falls back to L3 when unavailable)
- L6 live frontier smoke depends on API key presence

---

## How to update

1. Mark tasks `[x]` when merged to `main`; add commit hash in **Notes** when helpful.
2. Refresh **Last updated** and pytest count after test changes.
3. Do not mark done without implementation — check `daari/cli/`, `tests/`, and `git log`.
4. Keep Phase B+ as preview; detail stays in [ROADMAP](prd/ROADMAP.md) and [phase-a.md](plans/phase-a.md).
