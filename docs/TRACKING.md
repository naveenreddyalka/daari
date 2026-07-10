# daari — Task tracking

> Last updated: 2026-06-23  
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
| Cursor via tunnel setup | [x] | `scripts/tunnel.sh --setup-cursor` + `daari setup cursor --base-url/--tunnel` |
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

**Count:** 162 passed (`pytest -m "not integration and not benchmark"`, 2026-06-23)

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
| `daari setup all` auto-detect run | [x] | detects registered clients and runs applicable recipes |
| `daari setup intellij` | [x] | minimal IntelliJ helper config + dry-run + undo path |
| `daari setup vscode` | [x] | VS Code dry-run/apply/undo recipe with marker + docs |
| `daari setup claude-code` | [x] | minimal env helper + config pointer recipe with dry-run/apply |
| Lt ask/confirm UX | [x] | `daari_meta.confirmation_prompt` + `X-Daari-Confirm: yes` |
| Lt `--yes` support | [x] | `--yes` in prompt text now confirms unknown-policy commands |
| Doctor L4 pull hint | [x] | optional `model_l4` hint with pull command |
| Install optional L4/L5 pull flags | [x] | `daari install --pull-l4 --pull-l5` + `scripts/install.sh` env knobs |
| Eval expansion GP-11–GP-20 | [x] | prompts + regression assertions updated |

**Exit criteria (Phase B — partial)**

| Criterion | Status | Notes |
|-----------|--------|-------|
| Paraphrased prompt hits L1 | [x] | mocked embedder tests |
| L1 metrics in `daari stats` | [x] | tier counter `L1` |
| L0 → CCS → L1 → L2-dev → L2 → Lt → L3/L4 routing order | [x] | with tool_calls bypass caches retained |

**Tests:** see [Testing](#testing) below.

---

## Phase C bootstrap — in progress

| Task | Status | Notes |
|------|--------|-------|
| Gateway adapter protocol (`daari/gateway/base.py`) | [x] | OpenAI adapter now implements protocol |
| Anthropic gateway adapter (`/v1/messages`) | [x] | non-stream + SSE event streaming (`stream: true`) |
| MCP gateway ingress | [x] | `/v1/mcp/query` now supports `tools/list`, `tools/call`, and JSON-schema tool catalog |
| L5 local tier wiring | [~] | config + routing/escalation support; large model remains optional |
| Sourcegraph/GHE provider depth (C3) | [x] | Sourcegraph GraphQL + GHE repo/issue search with configurable base URLs and token envs |
| GitLab self-hosted provider depth (C3) | [x] | REST project/issue search + `@gitlab` trigger + MCP tool support |
| L2-live URL fetch | [x] | simple fetch trigger (`fetch/read/summarize/get <url>`) + L3 summarization |
| SSE metadata enrichment | [x] | stream chunks now include `daari_meta` tier/provider/model |
| Browser extension MVP | [x] | MV3 popup UI in `packages/browser-extension/` sends prompts to local daemon (`:11435`) |
| Browser extension options + error UX | [x] | API base URL options page + popup guidance when daemon is unreachable |
| Router integration prefixes | [x] | `@sourcegraph` / `@ghe` now route to integration providers before L3 |
| Per-project profiles | [x] | `~/.daari/profiles/<hash|slug>.yaml` + `DAARI_PROFILE` support |
| Skills loader stub | [x] | `~/.daari/skills/*.md` merged into system prompt prefix |
| Anthropic stream fallback | [x] | stream error now emits SSE error and falls back to non-stream response events |
| Web UI MVP dashboard | [x] | `daari web-ui serve` + static dashboard (`packages/web-ui/`) |
| Web UI auto-refresh + tier chart | [x] | dashboard now includes periodic refresh controls and tier distribution bars |
| Web UI export + theme controls | [x] | export current stats as JSON, dark/light toggle, and org-learning summary line |
| Enterprise scaffold | [x] | `daari/enterprise/` added with minimal `OrgSettings` models |
| Enterprise E1 runtime scaffold | [x] | org cache path resolver + `daari serve --org` + `DAARI_ORG_ID` + doctor org check |
| Enterprise E2 org shared cache service | [x] | `daari org-cache serve` + org cache client + router `L0-org/L1-org` lookup + write-through |
| `context clear` stale-cache warning | [x] | prints restart note when daemon is running to avoid stale in-memory cache handles |
| Hot cache reload endpoint | [x] | `POST /v1/daari/reload-caches` reloads cache handles in running daemon; `daari context clear` invokes it automatically |
| Enterprise periodic profile sync | [x] | startup + interval sync via `org.learning_sync_seconds`, plus force-sync endpoint/CLI |
| Org cache retry/backoff hardening | [x] | retries transient org cache failures with exponential backoff |
| L1 semantic threshold + bench hardening | [x] | default threshold tuned to `0.88`; `scripts/bench.sh` now deterministically checks L0 and L1 |
| Doctor embedding-model check | [x] | `daari doctor` now validates `cache.l1.embedding_model` (`nomic-embed-text`) |
| PyPI publish prep | [x] | enriched `pyproject.toml` metadata + `.github/workflows/publish.yml` for PyPI/TestPyPI |
| Cursor setup smoke script | [x] | `scripts/smoke-cursor-dry-run.sh` for CI/local setup dry-run validation |
| Cursor tunnel setup script | [x] | `scripts/tunnel.sh` starts local daemon + cloudflared and prints `/v1` URL |

---

## Cursor E2E BYOK — POC (2026-06-23)

Manual validation: **Cursor Ask + daari model via cloudflared tunnel → local Ollama**.  
Debug log: `~/.daari/cursor-requests.log` (request shape, tier attempts, `content_chunks`).

### Issues found & fixed (shipped 2026-06-23)

| Issue | Symptom | Fix | Status |
|-------|---------|-----|--------|
| Cursor blocks localhost | `Access to private networks is forbidden` | HTTPS tunnel (`scripts/tunnel.sh`) | [x] |
| Array message content (`[{"type":"text",...}]`) | 422 Unprocessable Entity | `content_to_text()` in gateway | [x] |
| Cursor `input_text` content blocks | Empty stream (~20ms), 0 `content_chunks` | `content_to_text()` handles `input_text`, `output_text`, dict blocks | [x] |
| Cursor sends 18 IDE tools on Ask | Ollama returns `tool_calls`, 0 text chunks | Strip `tools` in `_prepare_internal_request()` + plain-text system hint | [x] |
| `tool_calls` left in message history | Ollama 400, empty stream | `sanitize_messages_for_ollama()` when tools stripped | [x] |
| Stream path missing L4→L3 fallback | L4 404 when `llama3.1:8b` not pulled; empty or slow retry | `stream_openai_chunks()` tier chain + fallback (matches non-stream `route()`) | [x] |
| Stream error JSON malformed | Cursor freeze / parse errors | `json.dumps()` for stream errors; initial `role: assistant` chunk | [x] |
| Missing `/v1/models` | Cursor model picker issues | `GET /v1/models`, `GET /v1/models/{id}` | [x] |
| Gateway request logging | Hard to debug Cursor payloads | `~/.daari/cursor-requests.log` via `log_gateway_event()` | [x] |
| Integration tests for above | — | `tests/integration/test_gateway_flow.py`, `tests/unit/test_gateway_content.py` | [x] |

**Verified E2E:** Cursor `user_agent: Cursor/1.0` → daari → Ollama `llama3.2:3b` (L3 fallback) or `llama3.1:8b` (L4 when pulled); `content_chunks` > 0. Release notes: [RELEASE-v1.1.2-cursor-e2e.md](RELEASE-v1.1.2-cursor-e2e.md).

### Testing summary (2026-06-23)

| Layer | Result |
|-------|--------|
| `pytest` (default, mocked) | **162 passed**, 1 skipped |
| Manual Cursor Ask E2E | ✅ math question + follow-up |
| Log verification | ✅ `tools_stripped`, `stream_fallback_ok`, `content_chunks` > 0 |

### Next steps (Cursor / BYOK) — migrated to GitHub issues (2026-07-10)

The open rows below moved to the `auto-dev` backlog worked by the autonomous dev loop ([AUTOMATION.md](AUTOMATION.md)):

| Task | Issue |
|------|-------|
| ~~Commit Cursor compat fixes to `main`~~ | done (commit `1d651c6`) |
| ~~Document `cursor-requests.log` in setup/cursor.md~~ | done |
| Tool hallucination after tools stripped | [#1](https://github.com/naveenreddyalka/daari/issues/1) (P1) |
| Ask vs Agent mode split (ADR-0004) | [#2](https://github.com/naveenreddyalka/daari/issues/2) (P1) |
| Cursor-specific tier policy | [#3](https://github.com/naveenreddyalka/daari/issues/3) (P2) |
| Pull L4 in install by default | [#4](https://github.com/naveenreddyalka/daari/issues/4) (P3) |
| Anthropic stream usage + fallback parity | [#5](https://github.com/naveenreddyalka/daari/issues/5) (P2) |
| Org L1 semantic matching depth | [#6](https://github.com/naveenreddyalka/daari/issues/6) (P2) |
| Browser extension E2E coverage | [#7](https://github.com/naveenreddyalka/daari/issues/7) (P3) |
| Tag v1.1.2 release prep | [#8](https://github.com/naveenreddyalka/daari/issues/8) (P3) |
| Automated Cursor E2E test | covered by local watchdog (`scripts/autodev-local.sh`, Cursor-shaped smoke every 2h) |

---

## Autonomous dev loop (2026-07-10)

| Piece | Status | Notes |
|-------|--------|-------|
| Backlog seeded as `auto-dev` issues #1–#8 | [x] | priorities P1–P3, acceptance criteria per issue |
| AGENTS.md agent contract | [x] | repo root |
| Repo public + auto-merge + branch protection on main (CI `test` required) | [x] | via `gh api` |
| Local watchdog (`scripts/autodev-local.sh` + launchd) | [x] | validated live: filed issue #9 on first cycle (caught real live-test regression), Cursor smoke PASS |
| Cloud automation drafts (dev-cycle / pr-review / scout) | [x] | [docs/automations/](automations/) — create in Agents Window or enable Bugbot |
| CI fallback dev-cycle workflow | [x] | `.github/workflows/autodev.yml`; activates when `CURSOR_API_KEY` secret is set |
| Runbook | [x] | [AUTOMATION.md](AUTOMATION.md) |

---

## Phase E2 — Org shared cache (tracer bullet)

| Task | Status | Notes |
|------|--------|-------|
| Org cache HTTP service (`/get`, `/put`, `/stats`) | [x] | `daari/enterprise/service.py` |
| Router shared-cache lookup order (`L0-org`, `L1-org`) | [x] | local L0 -> org L0 -> local L1 -> org L1 |
| Shared write-through from local model responses | [x] | pushes L0 + L1 keys to org cache when configured |
| Config expansion (`org.id`, `shared_cache_url`, token, timeout) | [x] | `Settings.load` maps `org` block into `enterprise` |
| `daari serve --org` org-cache client wiring | [x] | `AppContext.from_settings` instantiates `OrgCacheClient` when URL set |
| Doctor org-cache reachability check | [x] | optional `org_cache` check (`/v1/org-cache/stats`) |
| Tests (service/client/router/config/cli) | [x] | no real network required in CI |
| E3 collective learning | [x] | metadata-only feedback API + profile sync + CLI stats/export |
| Web UI serve CLI smoke test | [x] | `tests/test_setup.py::test_web_ui_serve_mounts_static_assets` |

---

## Deferred / user-owned

- Cursor smoke test on personal device (`daari setup cursor` + chat through daari) — **Ask E2E verified 2026-06-23**; see [Cursor E2E BYOK POC](#cursor-e2e-byok--poc-2026-06-23)
- L4 model pull/install still user-managed (falls back to L3 when unavailable; pull `llama3.1:8b` to use L4 without retry)
- L6 live frontier smoke depends on API key presence
- Cursor follow-up quality / tool hallucination when tools stripped (tracked in open todos above)

---

## How to update

1. Mark tasks `[x]` when merged to `main`; add commit hash in **Notes** when helpful.
2. Refresh **Last updated** and pytest count after test changes.
3. Do not mark done without implementation — check `daari/cli/`, `tests/`, and `git log`.
4. Keep Phase B+ as preview; detail stays in [ROADMAP](prd/ROADMAP.md) and [phase-a.md](plans/phase-a.md).
