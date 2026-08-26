# daari — Task tracking

> Last updated: 2026-08-17 (v1.3.0 released — see [RELEASE-v1.3.0.md](RELEASE-v1.3.0.md))  
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
| **Integration (live Ollama)** | `tests/integration/test_ollama_live.py`, `test_sampling_live.py`, `test_client_path_live.py` | skipped | `@pytest.mark.integration`; run with `OLLAMA_HOST=http://127.0.0.1:11434 pytest -m integration` |
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

**Count:** 1007 passed (`pytest -m "not integration and not benchmark"`, 2026-08-26)

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
| $0-tier rate ≥30% on eval | [x] | Measured 2026-07-23 on GP-01–GP-20 mocked suite: **55%** $0-tier (L0/L1/CCS/L2/Lt) — see `scripts/measure_phase_b_metrics.py` |
| Routing accuracy ≥90% on 20-prompt eval | [x] | Same run: **100%** of eval assertions green (20/20) |

**Tests:** see [Testing](#testing) below.

---

## Phase C bootstrap — in progress

| Task | Status | Notes |
|------|--------|-------|
| Gateway adapter protocol (`daari/gateway/base.py`) | [x] | OpenAI adapter now implements protocol |
| Anthropic gateway adapter (`/v1/messages`) | [x] | non-stream + SSE event streaming (`stream: true`) |
| MCP gateway ingress | [x] | JSON-RPC 2.0 at `POST /mcp`; `/v1/mcp/query` deprecated alias |
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
| PyPI publish | [x] | `daari==1.2.0` is on [PyPI](https://pypi.org/project/daari/). Trusted publisher registered 2026-08-13; `python scripts/release_pypi.py publish --target pypi` reran the failed v1.2.0 job and `verify` installed from the index. Homebrew tap already pointed at the same tarball. · [#160](https://github.com/naveenreddyalka/daari/issues/160) |
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
| `pytest` (default, mocked) | **1007 passed** (2026-08-26) |
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

### Demo cycle (2026-07-10) — loop verified end-to-end

The first full autonomous cycle ran the same day the loop was built:

1. **Detect** — local watchdog's first run caught a real regression on `main` (live Ollama test asserting removed `daari_meta` default + a prompt failing the confidence heuristic) and filed [#9](https://github.com/naveenreddyalka/daari/issues/9) with logs, labels `auto-dev,regression`.
2. **Fix** — agent picked up #9 per AGENTS.md: branch `autodev/9-live-test-meta-headers`, fix + test runs (live: 1 passed; default: 161 passed), conventional commit.
3. **Gate** — PR [#10](https://github.com/naveenreddyalka/daari/pull/10) opened with `Closes #9`, auto-merge armed; branch protection held it until CI `test` went green.
4. **Merge** — auto-merged as `f12889a`; branch auto-deleted; issue #9 auto-closed.
5. **Validate** — next watchdog cycle on updated `main`: daemon healthy, integration tests PASS, Cursor smoke PASS (8 content chunks). `cycle result: PASS`.

### Loop cycles 2–3: P1 backlog cleared (2026-07-10)

| Issue | Fix | PR | Merge |
|-------|-----|----|-------|
| [#1](https://github.com/naveenreddyalka/daari/issues/1) tool hallucination | strengthened `NO_TOOLS_HINT` leads message list, idempotent | [#11](https://github.com/naveenreddyalka/daari/pull/11) | `4b35cfa` |
| [#2](https://github.com/naveenreddyalka/daari/issues/2) Ask vs Agent split | tool-history detection, `X-Daari-Tools` override, OpenAI `tool_calls` stream deltas | [#12](https://github.com/naveenreddyalka/daari/pull/12) | `f080150` |

### Feature cycle: v1.2 candidate set (2026-07-10)

Scouted against LiteLLM/RouteLLM feature sets; filed as issues #13–#15, implemented TDD-style, all auto-merged the same evening:

| Issue | Feature | PR | Merge |
|-------|---------|----|-------|
| [#13](https://github.com/naveenreddyalka/daari/issues/13) | Streaming L0 exact cache read/write + stream metrics (Cursor BYOK is stream-only; the cache never served it before) | [#16](https://github.com/naveenreddyalka/daari/pull/16) | `d4fe1ee` |
| [#14](https://github.com/naveenreddyalka/daari/issues/14) | Persistent usage ledger (`~/.daari/usage/ledger.sqlite3`) + `GET /v1/daari/report` + `daari report` CLI with `estimated_saved_usd` | [#17](https://github.com/naveenreddyalka/daari/pull/17) | `d9736f1` |
| [#15](https://github.com/naveenreddyalka/daari/issues/15) | Frontier daily budget guard (`frontier.daily_budget_usd`, warning `frontier_budget_exceeded`, spend surfaced in report) | [#18](https://github.com/naveenreddyalka/daari/pull/18) | `2e7ec56` |

Default suite grew 162 → 180 tests across these five cycles.

### Feature cycle: prompt intelligence & transparency (2026-07-10, PRD [docs/prd/intelligence.md](prd/intelligence.md))

Filed as issues #19–#22 from the new PRD, implemented TDD-style, all auto-merged, then validated end-to-end by a full `autodev-local.sh` cycle (deploy `ae3b01f`, live Ollama integration tests PASS, Cursor-shaped streaming smoke PASS) plus a live trace fetch (`daari trace` showed profile → l0_lookup → l1_lookup → tier_attempt → served for a real daemon request):

| Issue | Feature | PR | Merge |
|-------|---------|----|-------|
| [#19](https://github.com/naveenreddyalka/daari/issues/19) | Prompt profile (category/complexity/token est) + `routing.category_policies` action policies; category in `daari_meta.task_type`, new `complexity` | [#23](https://github.com/naveenreddyalka/daari/pull/23) | `ed43d21` |
| [#20](https://github.com/naveenreddyalka/daari/issues/20) | Per-request decision trace: `TraceStore` sqlite, `daari_meta.trace_id`, `GET /v1/daari/traces[/id]`, `daari trace` CLI (client-facing audit trail) | [#24](https://github.com/naveenreddyalka/daari/pull/24) | `cb80d4a` |
| [#21](https://github.com/naveenreddyalka/daari/issues/21) | Cached-draft injection: L1 near-misses (`cache.l1.draft_threshold`=0.75) seed local and L6 generation as reuse/reformat drafts | [#25](https://github.com/naveenreddyalka/daari/pull/25) | `e4126d4` |
| [#22](https://github.com/naveenreddyalka/daari/issues/22) | Context optimizer: system + last-N history trimming and whitespace squeeze for local models (`context_optimizer.*`), savings traced per prompt | [#26](https://github.com/naveenreddyalka/daari/pull/26) | `ae3b01f` |

Default suite now at 226 tests (180 → 226).

### Loop cycles: original backlog cleared (#3–#6) (2026-07-10)

The remaining seeded issues from the first backlog, implemented TDD-style, auto-merged, and each validated live by a full `autodev-local.sh` cycle (final deploy `a8600cc`, live Ollama integration tests PASS, Cursor-shaped streaming smoke PASS):

| Issue | Feature | PR | Merge |
|-------|---------|----|-------|
| [#3](https://github.com/naveenreddyalka/daari/issues/3) | Tier cap for chat: `routing.max_tier_for_chat` + `X-Daari-Tier-Cap` header clamp initial tier, stream chain, and local escalation (latency recipe in docs/setup/cursor.md) | [#28](https://github.com/naveenreddyalka/daari/pull/28) | `9da32c4` |
| [#4](https://github.com/naveenreddyalka/daari/issues/4) | `daari setup cursor` verifies/pulls the L4 model (`--yes` for non-interactive; tunnel.sh passes it); `daari doctor` upgrades `model_l4` to required when Cursor is configured | [#29](https://github.com/naveenreddyalka/daari/pull/29) | `79b3221` |
| [#5](https://github.com/naveenreddyalka/daari/issues/5) | Anthropic stream parity: tier fallback chain, message sanitization, chars/4 usage estimates in `message_start`/`message_delta` | [#30](https://github.com/naveenreddyalka/daari/pull/30) | `a956d33` |
| [#6](https://github.com/naveenreddyalka/daari/issues/6) | Org L1 semantic matching: embeddings stored with entries, `POST /v1/org-cache/similar`, client similarity fallback on key miss (paraphrases now hit `L1-org`) | [#31](https://github.com/naveenreddyalka/daari/pull/31) | `a8600cc` |

Default suite now at 250 tests (226 → 250). Remaining open backlog: #7 (browser-extension E2E), #8 (v1.1.2 release prep — tagging stays human-approved).

### Loop cycles: extension coverage + scouted improvements (#7, #34–#36) (2026-07-10)

After clearing the original backlog, the loop scouted and filed three fresh improvement issues (#34–#36), then implemented all of them plus #7. Each cycle E2E-validated by `autodev-local.sh` (final deploy `984bc99`); markdown export and cache prune also verified live against the running daemon:

| Issue | Feature | PR | Merge |
|-------|---------|----|-------|
| [#7](https://github.com/naveenreddyalka/daari/issues/7) | Browser extension DOM tests (jsdom + node --test, 12 tests: send flow, error UX, draft persistence, options); new `extension` CI job | [#33](https://github.com/naveenreddyalka/daari/pull/33) | `aa6602d` |
| [#34](https://github.com/naveenreddyalka/daari/issues/34) | Frontier prompt slimming before L6: strip internal hints, collapse duplicate system prompts, trim history; ledger records actual chars sent (`frontier.slim_prompts`) | [#37](https://github.com/naveenreddyalka/daari/pull/37) | `e27e930` |
| [#35](https://github.com/naveenreddyalka/daari/issues/35) | Client-shareable markdown export: `daari report`/`daari trace` gain `--format markdown` + `--out FILE` | [#38](https://github.com/naveenreddyalka/daari/pull/38) | `78a0066` |
| [#36](https://github.com/naveenreddyalka/daari/issues/36) | Cache TTLs (`cache.l0/l1.ttl_seconds`, category `ttl_seconds` overrides) + `daari cache prune` | [#39](https://github.com/naveenreddyalka/daari/pull/39) | `984bc99` |

Default suite now at 272 pytest tests (250 → 272) + 12 extension tests. Open backlog: #8 (release prep, human-gated).

### v1.1.2 released + CI hardening (2026-07-11)

- CI expanded to four required checks on `main`: `test`, `extension`, `lint` (ruff), `sanity` (runtime-deps install, imports, settings load, CLI entrypoint, app build) — [#41](https://github.com/naveenreddyalka/daari/pull/41), `97cb5e1`.
- **v1.1.2 shipped** (issue [#8](https://github.com/naveenreddyalka/daari/issues/8), user-approved tag): version bump (pyproject + stale `daari.__version__`), consolidated release notes addendum, `python -m build` + `twine check` PASSED (no PyPI upload) — [#42](https://github.com/naveenreddyalka/daari/pull/42), tag [`v1.1.2`](https://github.com/naveenreddyalka/daari/releases/tag/v1.1.2).

### Loop cycles: streaming L1 + scouted improvements (#43–#46) (2026-07-11)

Scout pass filed four issues; all implemented TDD-style, auto-merged, and E2E-validated by `autodev-local.sh` on the final deploy `531e407` (live Ollama integration tests PASS, Cursor streaming smoke PASS; daemon restarted on the new build and `/v1/daari/report` verified live):

| Issue | Feature | PR | Merge |
|-------|---------|----|-------|
| [#43](https://github.com/naveenreddyalka/daari/issues/43) | Streaming path L1 parity: semantic hits served as SSE, draft-band injection, post-`[DONE]` L1 write-back — Cursor (all-streaming) finally benefits from the semantic cache | [#47](https://github.com/naveenreddyalka/daari/pull/47) | `1f3d963` |
| [#44](https://github.com/naveenreddyalka/daari/issues/44) | Gateway request log rotation: size-based with numbered backups (`observability.request_log_max_bytes`, default 5 MB / 3 backups) | [#48](https://github.com/naveenreddyalka/daari/pull/48) | `121aa43` |
| [#45](https://github.com/naveenreddyalka/daari/issues/45) | Embedding memoization: in-process LRU in `OllamaEmbedder` keyed by (model, sha256) — repeat L1 lookups skip the Ollama HTTP call (`cache.l1.embed_cache_size`) | [#49](https://github.com/naveenreddyalka/daari/pull/49) | `b3e4596` |
| [#46](https://github.com/naveenreddyalka/daari/issues/46) | Web UI usage & savings dashboard: report totals, per-day tier table, recent traces with step-timeline click-through; jsdom DOM suite added to CI | [#50](https://github.com/naveenreddyalka/daari/pull/50) | `531e407` |

Default suite now at 291 pytest tests (272 → 291) + 12 extension tests + 7 web-ui tests. Open backlog: empty — scout refills it.

### Phase D1 — personal feedback loop (2026-07-11, PRD [docs/prd/learning.md](prd/learning.md))

daari starts learning from outcomes. Everything stays on-device
(`~/.daari/feedback/feedback.sqlite3`) and stores outcome metadata only —
never prompt or completion text. PRD merged as [#52](https://github.com/naveenreddyalka/daari/pull/52).

| Issue | Feature | PR | Merge |
|-------|---------|----|-------|
| [#53](https://github.com/naveenreddyalka/daari/issues/53) | Outcome store + implicit capture (every model-tier response, stream + non-stream, not cache hits) + explicit `POST /v1/daari/feedback` / `daari feedback <trace_id> --accept\|--reject` | [#56](https://github.com/naveenreddyalka/daari/pull/56) | `b272153` |
| [#54](https://github.com/naveenreddyalka/daari/issues/54) | `daari learn stats` per-category × tier evidence + `daari learn recommend` (cheapest tier with escalation ≤ 15%, rejects ≤ 10%, min 20 samples) emitting a Settings-valid `routing.category_policies` YAML block; `GET /v1/daari/learn/stats` | [#57](https://github.com/naveenreddyalka/daari/pull/57) | `62dbf24` |
| [#55](https://github.com/naveenreddyalka/daari/issues/55) | Routing tuner: per-category confidence thresholds ±0.05 from outcome evidence, bounded [0.5, 0.9], `learning.tuner_min_samples` gate, `tuner` trace step; off by default (`learning.auto_tune`) | [#58](https://github.com/naveenreddyalka/daari/pull/58) | `518e8ae` |

Live E2E validated 2026-07-11: daemon restarted on `518e8ae`; live doc_qa
request through the gateway → `daari feedback <trace_id> --accept` →
outcome + accept visible in `daari learn stats`; `daari learn recommend`
emitted a valid policy block from live evidence. Default suite now at 329
pytest tests (291 → 329). Remaining Phase D scope (D2 local fine-tuning,
D3 opt-in collective stats) stays on the roadmap.

### Phase D2 — local fine-tuning train (2026-07-12, PRD [docs/prd/learning.md](prd/learning.md))

The models themselves can now improve. Accepted answers — especially L6
frontier answers — become local training data (distillation). Capture is
strictly **opt-in** (`learning.capture_examples`, default off) because unlike
the D1 outcome store it keeps full prompt/completion text; everything stays
under `~/.daari/training/` and is wipeable. PRD merged as [#60](https://github.com/naveenreddyalka/daari/pull/60).

| Issue | Feature | PR | Merge |
|-------|---------|----|-------|
| [#61](https://github.com/naveenreddyalka/daari/issues/61) | `ExampleStore` + router capture (both paths, L3–L6, never cache hits/tool flows); accept promotes to training data, reject deletes; `daari learn examples [--clear]` | [#64](https://github.com/naveenreddyalka/daari/pull/64) | `0144b17` |
| [#62](https://github.com/naveenreddyalka/daari/issues/62) | `daari learn export-dataset`: mlx-lm chat-format train/valid JSONL, deterministic trace_id-hash split, min-examples gate, `--only-accepted` | [#65](https://github.com/naveenreddyalka/daari/pull/65) | `eb7104d` |
| [#63](https://github.com/naveenreddyalka/daari/issues/63) | `daari learn finetune`: plans + runs `mlx_lm lora --train` (LoRA on `mlx-community/Llama-3.2-3B-Instruct-4bit`), auditable run.json, `--dry-run`, clean optional-dep gating | [#66](https://github.com/naveenreddyalka/daari/pull/66) | `1d4cdb5` |

Live E2E validated 2026-07-12 on an isolated temp instance (capture on,
throwaway stores — user config untouched): 10 live Ollama requests captured,
2 accepted + 1 rejected via `/v1/daari/feedback` (reject confirmed deleted),
`export-dataset` produced 8 train / 1 valid chat-format examples, and
`plan_finetune` emitted the exact `mlx_lm lora` command + run.json. Default
suite now at 359 pytest tests (329 → 359). Actual training runs are
user-invoked (`daari learn finetune`, needs `pip install mlx-lm`); serving
MLX adapters through Ollama (fuse/convert to GGUF) is the documented manual
follow-up. Remaining Phase D scope: D3 opt-in collective stats.

### Trust & Efficiency trains (2026-07-12/13, PRD [docs/prd/trust.md](prd/trust.md))

Competitive research (Portkey/LiteLLM/OpenRouter/Requesty/RouteLLM, semantic-
cache postmortems, local-first routers) distilled into five trains. Headline:
daari now **measures semantic-cache false-hit rate** — the metric none of the
compared products ship. PRD merged as [#68](https://github.com/naveenreddyalka/daari/pull/68).

| Issue | Train | PR | Merge |
|-------|-------|----|-------|
| [#69](https://github.com/naveenreddyalka/daari/issues/69) | **Cache trust**: embedding-input normalization (fences/JSON scaffolding stripped, `cache.l1.normalize_inputs`); per-category answer-diversity monitor (`/v1/daari/cache/diversity` + doctor warning); shadow sampling of L1 hits (`cache.l1.shadow_sample_rate`, default 5%) → per-category false-hit rate that auto-raises the L1 threshold; report/`learn stats`/dashboard panels | [#70](https://github.com/naveenreddyalka/daari/pull/70) | `7721b25` |
| [#71](https://github.com/naveenreddyalka/daari/issues/71) | **Token savings**: Anthropic `cache_control` prompt-cache hint on L6 with byte-stable prefix pinned by test; `context_optimizer.compact` — over-limit history summarized by L3 into a pinned recap (memoized per prefix); `frontier.compress_context` — sentence-level relevance pruning before L6 | [#75](https://github.com/naveenreddyalka/daari/pull/75) | `da4fabf` |
| [#72](https://github.com/naveenreddyalka/daari/issues/72) | **Latency-aware routing**: `daari profile` hardware benchmarks; `routing.latency_budget_ms` + category override + `X-Daari-Latency-Budget` with profiled step-down; warm-model preference via TTL-cached `/api/ps` | [#79](https://github.com/naveenreddyalka/daari/pull/79) | `4c365d9` |
| [#73](https://github.com/naveenreddyalka/daari/issues/73) | **Learned routing**: `daari learn train-router` centroid classifier over captured prompts; `routing.learned_router` overrides heuristics when confident (200-sample floor + margin gate); trace `learned_route` | [#79](https://github.com/naveenreddyalka/daari/pull/79) | `4c365d9` |
| [#74](https://github.com/naveenreddyalka/daari/issues/74) | **Budget & client UX**: monthly + soft budgets (`frontier_budget_warning` band before hard cap); per-client ledger attribution (`X-Daari-Client-Id`, Cursor auto-tagged) + `daari report --by-client`; opt-in pre-L6 PII scrub with typed placeholders | [#79](https://github.com/naveenreddyalka/daari/pull/79) | `4c365d9` |

Trains 3–5 were consolidated into [#79](https://github.com/naveenreddyalka/daari/pull/79)
after the stacked branches went stale post-squash (#76–#78 closed as superseded).
Live E2E validated 2026-07-13 on an isolated temp instance (port 11438, live
Ollama, throwaway stores): paraphrase served from L1 with normalization on,
shadow check ran in background (answer similarity 0.984 → agreed, false-hit
rate 0.0 in `learn stats`/report/diversity endpoints), per-client attribution
(`e2e-test`) and budget state in the report, and `benchmark_model` + warm
tracker measured the live 3B model (349 ms wall, 115 tok/s, warm set
detected). Default suite 430 pytest tests (359 → 430); web-ui at 9 DOM tests.
All new behaviors default-safe: normalization + shadow sampling on (read-only
additions), compaction/compression/learned-router/PII-scrub opt-in.

### One-click client setup (2026-07-13, issue [#81](https://github.com/naveenreddyalka/daari/issues/81))

| Item | PR | Merge |
|------|----|-------|
| **Claude Code one-click**: `daari setup claude-code` merges `ANTHROPIC_BASE_URL`/`ANTHROPIC_AUTH_TOKEN`/`ANTHROPIC_MODEL` into the `env` block of `~/.claude/settings.json` (existing keys preserved, backup + undo); Anthropic gateway now honors the top-level `system` field (string or blocks) that Claude Code sends. **Ollama-compatible facade**: `/api/tags`, `/api/chat` (stream NDJSON + non-stream), `/api/version`, `/api/show`, `/api/ps` — JetBrains AI Assistant, Zed, Continue etc. connect by pasting `http://127.0.0.1:11435`, full router semantics + per-client attribution (`X-Daari-Client-Id`). IntelliJ recipe/docs updated with exact AI Assistant steps; native IntelliJ plugin deferred in favor of the facade. | [#82](https://github.com/naveenreddyalka/daari/pull/82) | `bbe233e` |

Live-verified 2026-07-13 on the running daemon: `/api/tags` lists `daari` +
tier models, non-stream `/api/chat` answered from L3 with `daari_meta`, and the
`intellij` client id landed in the ledger. The tool-passthrough limit noted at
the time was closed the same day by issue #84 (below). Suite: 442 pytest tests.

### Claude Code agent E2E + tunnel hardening (2026-07-13, issues [#84](https://github.com/naveenreddyalka/daari/issues/84)/[#86](https://github.com/naveenreddyalka/daari/issues/86)/[#88](https://github.com/naveenreddyalka/daari/issues/88))

| Item | PR | Merge |
|------|----|-------|
| **Anthropic tool passthrough**: `tools`/`tool_choice` on `/v1/messages`, `tool_use`→`tool_calls` and `tool_result`→`role:tool` conversion, agent flows skip sanitization/context-optimizer, streamed `tool_use` content blocks with `stop_reason: "tool_use"`; `X-Daari-Tools: strip` forces plain chat; one-click uninstall fallback strips daari `ANTHROPIC_*` keys when no backup exists | [#85](https://github.com/naveenreddyalka/daari/pull/85) | `1e2934c` |
| **Gateway API-key auth**: `server.api_key` setting + middleware (Bearer or `x-api-key`, health endpoints exempt); `daari setup cursor --tunnel` auto-generates + persists the key and configures Cursor with it; docs on named Cloudflare tunnels / Tailscale Funnel | [#87](https://github.com/naveenreddyalka/daari/pull/87) | `b594500` |
| **Claude Code live E2E fixes** (first real session surfaced 3 gaps): `OllamaRequestError` preserves Ollama 400 bodies in logs; `num_ctx` sized from prompt chars (4096..32768) so 10-20k-token Claude Code system prompts stop yielding empty streams; tool-call arguments converted JSON-string→object and content-less non-tool messages dropped (both 400'd Ollama); `anthropic_messages_request` shape logging | [#89](https://github.com/naveenreddyalka/daari/pull/89) | `8265b21` |

### Loop cycle 2026-07-22 — full live E2E + per-project profiles ([#91](https://github.com/naveenreddyalka/daari/issues/91))

Regression issue #90 closed as transient: the working tree sat on a dev branch
Jul 13–22 so the watchdog skipped deploys; its own kickstart recovered the
daemon in the same run. Daemon redeployed on `main @ 8265b21`, then the full
live battery passed 11/11 against the running daemon: OpenAI fresh→L3,
repeat→L0, stream SSE+DONE, Anthropic non-stream with `system`, streamed
`tool_use` + `stop_reason`, facade `/api/tags` + `/api/chat`, stats/report/
traces/diversity endpoints. Full suite 474 pytest + ruff + extension/web-ui
npm suites green.

**Per-project profiles** (roadmap Phase C1's last unshipped item): commit a
`.daari.yaml` at the repo root (`routing.max_tier_for_chat`, `no_frontier`,
`latency_budget_ms`, `client_id`); clients opt in with `X-Daari-Project:
/path/inside/repo` on both OpenAI and Anthropic gateways (the Anthropic
gateway also gained `X-Daari-Client-Id` parity). Explicit headers always win;
profiles are mtime-cached and malformed files never break a request. New CLI:
`daari project init` / `daari project show`. Docs:
[setup/project-profiles.md](setup/project-profiles.md).

### Release v1.2.0 + Claude Code live fix (2026-07-23)

| Item | PR | Merge |
|------|----|-------|
| **Release v1.2.0 — Learning, Trust & Clients**: version bump + [RELEASE-v1.2.0.md](RELEASE-v1.2.0.md) covering the 26 commits since v1.1.2 (Phase D learning, Trust trains, one-click clients, gateway auth, per-project profiles); tagged and [published](https://github.com/naveenreddyalka/daari/releases/tag/v1.2.0) | [#93](https://github.com/naveenreddyalka/daari/pull/93) | `6bfc9e3` |
| **Trailing system message fix** (issue [#94](https://github.com/naveenreddyalka/daari/issues/94)): live `claude -p` printed nothing — claude-cli 2.1.215 sends `messages=[user, system]` (SessionStart-hook/plugin content as a 14k-char trailing system-role message) and llama chat templates emit zero tokens in that shape, so L4 and L3 both streamed empty. Captured via a recording proxy; Anthropic gateway now hoists out-of-order system messages ahead of the conversation (stable order, leading-system requests untouched) | [#95](https://github.com/naveenreddyalka/daari/pull/95) | `bab511c` |

Suite: 493 pytest. The #94 regression test replays the captured Claude Code
request shape (top-level `system` + `[user, system]` + tools) and asserts
Ollama receives `[system, system, user]`. Live `claude -p` re-verification
runs on the next watchdog deploy cycle.

### MLX backend + CI hardening (2026-07-23, issue [#97](https://github.com/naveenreddyalka/daari/issues/97))

| Item | PR | Merge |
|------|----|-------|
| **MLX backend** (roadmap C2 optional): `MLXExecutor` speaks OpenAI wire to `mlx_lm.server` and duck-types `OllamaExecutor` (SSE chunks converted to Ollama-style events), so tier loops/caching/escalation/budgets/traces are unchanged; `mlx.models` tier→model map routes only listed tiers to MLX (mixed setups fine, default off); optional `daari doctor` mlx check; [setup/mlx.md](setup/mlx.md) | [#98](https://github.com/naveenreddyalka/daari/pull/98) | `5270dd4` |
| **CI ruff pin**: lint job installed unpinned `ruff>=0.8`; a new ruff release flagged 167 pre-existing issues repo-wide and failed every open PR — pinned to `ruff==0.15.17` (local version, clean) so lint is deterministic and upgrades become deliberate PRs | [#99](https://github.com/naveenreddyalka/daari/pull/99) | `b1c2385` |

Suite: 508 pytest (493 → 508). MLX live smoke is hardware/download-gated
(`pip install mlx-lm` + model fetch) — doctor and docs cover the path.

### Anthropic observability + Phase D3 + adapter deploy (2026-07-23, issue [#101](https://github.com/naveenreddyalka/daari/issues/101))

| Item | PR | Merge |
|------|----|-------|
| **Anthropic stream observability & routing parity** (issue #101): `anthropic_stream_attempt_failed` logs `error_type` (timeouts stringify to `""`), new `anthropic_stream_done` event records winning tier/model/latency/chars, and the Anthropic path now builds the prompt profile so category policies, learned routing, and latency-budget step-down apply like the OpenAI path | [#102](https://github.com/naveenreddyalka/daari/pull/102) | `e4628f4` |
| **Phase D3 — opt-in collective stats** ([learning PRD](prd/learning.md)): `daari learn export-stats` prints the exact metadata-only payload for review (category/tier aggregates, shadow false-hit rates, model IDs — never prompts/IDs); `--upload` gated on `learning.collective_enabled` + `collective_url` with a recursive sensitive-key guard; all defaults off | [#102](https://github.com/naveenreddyalka/daari/pull/102) | `e4628f4` |
| **`daari learn deploy`**: bridges D2c fine-tune runs to executors — mlx backend prints the `mlx_lm server --adapter-path` command + config snippet (long-running, plan-and-print); ollama backend fuses to GGUF and `ollama create`s a named model with `deploy.json` status audit | [#102](https://github.com/naveenreddyalka/daari/pull/102) | `e4628f4` |

Suite: 535 pytest (508 → 535). Live E2E on the redeployed daemon:
`/v1/messages` stream answered via L3 in 2.2s and `anthropic_stream_done`
appeared in cursor-requests.log; `learn export-stats` rendered real
30-day aggregates (metadata only); `learn deploy` printed correct mlx and
ollama plans against a stub run dir.

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
- PyPI upload remains **user-gated** (needs PyPI token in repo secrets)

---

## Roadmap v2 (F1–F5) — 2026-07-23/24

Forward plan: [ROADMAP-v2.md](prd/ROADMAP-v2.md). Issues labeled `auto-dev`.

| Train | Status | Notes |
|-------|--------|-------|
| F1 OSS launch | [x] | Docker/compose/`/ready` (#105), MkDocs (#114), PyPI prep (#106, upload user-gated), CHANGELOG + community pack |
| F2 Gateway parity | [x]/[~] | Responses API (#108), Prometheus (#107), guardrails (#110), capability catalog (#113); L6 pool (#109), virtual keys (#111) in flight / merged via auto-dev PRs |
| F3 Ops | [x] | Prometheus + Grafana (#107); OTel export + structured stdout logs + `GET/PATCH /v1/daari/config` (#115) |
| F4 Enterprise scale | [x] | Redis L0 (#112); Postgres ledger/traces + `observability.stateless` (#116); Helm + capacity (#117); org pool + `daari enterprise bootstrap` (#118); SSO/RBAC/audit tracer (#119) |
| F5 Leftovers | [x] | Live sources (#120); MCP egress (#121); Phase B exit metrics recorded above + `scripts/measure_phase_b_metrics.py` (#122); Homebrew formula (#123, sha256 filled after release) |

Suite: 669 pytest (default markers).

### Auto-mode deepeners (2026-07-24) — **reviewed 2026-08-11**

See [HANDOFF-AUTO-2026-07.md](HANDOFF-AUTO-2026-07.md). Built as tracer deepeners with review deferred; the frontier review pass landed as issue #137 (see below).

| Item | Status | Notes |
|------|--------|-------|
| Periodic org policy sync in daemon | [x] | `policy_sync.py` + learning sync loop |
| Config editor persist to disk | [x] | `persist: true` on PATCH; atomic 0600 write |
| D4 `propose-defaults` | [x] | YAML proposal only — never auto-promote |
| Web UI config card | [x] | Bearer field added in #141 |
| Strong-model review | [x] | #137 — see review pass below |
| PyPI upload / Homebrew sha256 | [ ] | User-gated (needs a release tarball) |
| Redis L1 semantic (`cache.backend=redis`) | [x] | #135 — `RedisSemanticCache`, tags `fable-review/135-*` |
| OIDC JWKS admin SSO | [x] | #136 — tags `fable-review/136-*`; HMAC stub retained |
| Web UI Bearer / API key field | [x] | #141 — tags `fable-review/141-*` |
| Live Redis+Postgres compose E2E | [x] | #142 — profile `backends` + `scripts/smoke_backends.py` / `.sh` |
| F6 Product boundaries (scope gate) | [x] | #145 — ADR-0015; B0+B1+config; tags `fable-review/boundaries-*` (triple-verify) |

### Frontier review pass (2026-08-11, issue #137)

Review of everything built while the deep-review pass was deferred. Defects fixed
in `tests/unit/test_review_hardening_137.py` (15 tests, all previously red):

| Defect | Severity | Fix |
|--------|----------|-----|
| Daemon policy sync applied **unsigned** org config when no signing secret was set (CLI path already failed closed) | high | `sync_policy_once` requires a secret unless `insecure=True` |
| Policy sync accepted plaintext `http://` for config that can disable guardrails and raise budgets | high | `policy_url_is_secure()` — https, or http to loopback only |
| Blocking `httpx` fetch ran on the event loop, stalling in-flight requests for up to the 10s timeout | medium | `asyncio.to_thread` in the sync loop |
| Sync failures were swallowed by `except Exception: pass` — no way to see a broken policy feed | medium | `log_gateway_event("policy_sync_failed"/"policy_sync_skipped")` |
| `daari learn propose-defaults` read a `{category: {accept_rate, n}}` shape that `build_collective_stats` never emits, so every run wrote an empty proposal and reported success | medium | `_flatten_category()` derives accept rate + sample count from the real nested `categories` payload; flat shape still supported |
| `~/.daari/config.yaml` written non-atomically at umask default, next to provider API keys | medium | `write_config_atomically()` — temp file + `os.replace`, mode 0600 (also used by `enterprise bootstrap`) |
| Cached JWKS locked admins out for the full TTL after an IdP key rotation | medium | refetch once with `force=True` on unknown `kid` |
| `PATCH /v1/daari/config` returned 500 on malformed values and half-applied out-of-range ones; `setattr` bypassed pydantic validation | medium | `daari/config/validate.py` validates the whole patch first → 400 |

`validate_assignment` on Settings closed in [#152](https://github.com/naveenreddyalka/daari/issues/152).
EC/ES256 JWKS keys closed in [#151](https://github.com/naveenreddyalka/daari/issues/151).
Redis L1 lost-update is [#150](https://github.com/naveenreddyalka/daari/issues/150).

### Streaming policy parity (#154, #155) (2026-08-11)

A feature-gap audit found that boundaries, guardrails, and frontier escalation ran
only in `Router.route()`. Both streaming entry points were separate code paths that
called none of them — so for every supported IDE client, which streams by default,
those features were inert. Reproduced before the fix: the same prompt with
`boundaries.mode = "block"` returned `tier='boundary'` with zero upstream calls
through `route()`, but streamed model output with no refusal.

| Defect | Severity | Fix |
|--------|----------|-----|
| Boundary gate never ran on either stream path — a `block`-mode refusal was silently skipped for all IDE traffic | high | `_apply_input_policy()` shared by `route()` and both stream paths |
| Input guardrails never ran on either stream path | high | same shared gate; refusals emitted as well-formed terminal streams (OpenAI `[DONE]`, Anthropic `message_stop`) |
| Output guardrails never ran on streams, so a leaked secret reached the client **and** was written to L0/L1 | high | `_apply_output_policy()` runs over accumulated text before flush and before cache write-back |
| `_stream_tier_chain` was local-model-only, so a streaming request could never reach the org pool or L6 | high | streams call `_maybe_escalate(..., local_ladder=False)` — org pool and frontier now reachable |

`local_ladder=False` is deliberate: `_stream_tier_chain` has already chosen and
fallen back through the local tiers, so re-running L4/L5 non-streamed would only
duplicate work. Non-streaming keeps the full local ladder.

Covered by `tests/unit/test_stream_policy_parity.py` (11 tests, 5 previously red).

### Streaming tier parity (#155) (2026-08-11)

Follow-up that closed the rest of the streaming gap.

| Defect | Severity | Fix |
|--------|----------|-----|
| Deterministic tiers (`Lt` shell tools, L2 rules, live fetch, integrations) were unreachable while streaming — the same prompt got a model answer instead of tool output | high | `_resolve_deterministic_tier()` extracted from `_route_impl` and called from both stream paths |
| Escalated streams buffered the whole frontier answer before emitting, so first-token latency was non-streaming latency | medium | `FrontierExecutor.stream()` relays upstream SSE; the router relays it chunk-by-chunk |

`_route_impl` is now three named steps (deterministic tiers → generation →
escalation) rather than one long function, which is what let the stream paths
reuse the same logic instead of reimplementing a subset of it.

The relay is skipped, falling back to the buffered path, when the complete text
is needed first: output guardrails must see the whole answer to redact it, and
the org pool has to be tried before paying for frontier. Both are explicit
checks in `_can_relay_frontier_stream()`.

Covered by `tests/unit/test_stream_tier_parity.py` (7 tests, 4 previously red),
including a `MockTransport` case proving the SSE decoder skips blank, malformed,
and `[DONE]` lines.

### Real token accounting and per-model pricing (#156, #157) (2026-08-11)

Every token count in daari was `len(chars) // 4`, and every cost was that
estimate multiplied by one flat `frontier.price_per_1k_tokens`. Two compounding
approximations fed the savings report, the `/v1/daari/report` endpoint, the
Prometheus spend gauges, and the budget cutoff that decides whether to escalate.

| Defect | Severity | Fix |
|--------|----------|-----|
| Providers report real usage (Ollama `prompt_eval_count`/`eval_count`, OpenAI `usage`) and none of it was read | high | `daari/observability/tokens.py` readers; captured into `DaariMeta.input_tokens`/`output_tokens` on both non-streaming and streaming paths |
| Clients received chars/4 in the `usage` block with no way to tell it was a guess | medium | real counts when reported; `daari_meta.usage_estimated` says which it was |
| One flat rate priced every model and both directions, so a gpt-4o output token and a gpt-4o-mini input token cost the same | high | `daari/pricing.py` with per-model, per-direction USD/1M rates; `pricing.models` in config |
| Ledger stored only chars, so spend could not be recomputed per model after the fact | medium | `usage`/`client_usage` gain `model`, `provider`, `input_tokens`, `output_tokens` |

Output tokens cost 4-5x input tokens at every major provider, so pricing both
directions at one blended rate was the largest single source of error.

The ledger migration rebuilds `usage` and `client_usage` rather than using
`ALTER TABLE ADD COLUMN`: the upsert needs `(day, tier, model)` as its conflict
target and SQLite cannot alter a primary key in place. Existing rows are copied
across with `model = ''`, which prices them at the fallback rate — historical
rows never had a model recorded, so no precision is lost that existed before.

Unpriced models still work: they fall back to the flat rate and `daari doctor`
prints a warning naming the model, so silently-wrong spend is visible rather
than discovered on a bill. The shipped price table is a dated convenience
default and `pricing.models` always overrides it.

Covered by `tests/unit/test_token_accounting.py` (15 tests) plus an
integration test asserting reported counts survive from executor to both the
API `usage` block and the ledger columns.

### L1 hit verification before serving (#168) (2026-08-11)

daari measured its semantic-cache false-hit rate but still served any hit above
a cosine threshold. Correct and incorrect similarity distributions overlap, so a
threshold cannot separate the two cases: "what is 15% of 200" and "what is 15%
of 300" are textually near-identical with different answers, while "how do I
list files" and "how can I list files" are further apart with the same answer.
Embedding distance ranks those two pairs in the wrong order.

`cache.l1.verify` (`none | lexical | model`, default `lexical`) adds a second
stage between the cosine match and the response. The lexical verifier rejects
differing numbers, differing or reordered units, flipped negations, swapped
opposites, and substituted content words; rejections fall through to generation
and increment `daari_cache_false_hits_avoided_total`.

Two deliberate choices worth knowing:

- **Entries without stored prompt text are not served.** Caches written before
  this change have no text to verify against, and serving them unverified would
  preserve exactly the false hits this exists to prevent. They are re-learned on
  the next miss, so the cost is a one-time warm-up.
- **Additions pass, substitutions do not.** Extra words are filler; a swapped
  word may change the answer.

The known limitation is honest and tracked rather than hidden: a lexical stage
cannot distinguish a harmless synonym substitution ("fix" for "resolve") from a
meaningful one ("staging" for "production"), because both are one-word swaps. It
errs toward regeneration and loses those hits. `verify = "model"` is the path to
recovering them.

`evals/cache/verification.jsonl` labels 36 pairs and runs in CI as a gate:
paraphrase retention and near-miss rejection both floor at 90%, currently 100%
each, with synonym retention reported but ungated at 0/6. Verification costs
0.007 ms per call against the hundreds of milliseconds a hit saves.

Covered by `tests/unit/test_l1_verification.py` (21 tests) and
`tests/unit/test_l1_verification_corpus.py` (4 gates).

---

### Per-key frontier budgets ([#158](https://github.com/naveenreddyalka/daari/issues/158))

Virtual-key budgets were compared against **global** frontier spend. The
middleware said so in its own comment: the ledger had no per-client frontier
helper, so it used the global figure "conservatively". The effect was that one
key's traffic exhausted every other key's allowance, and a key with a small cap
could be blocked by spend it never caused — while per-key budgets were a headline
feature of the virtual-keys work ([#111](https://github.com/naveenreddyalka/daari/issues/111)).

`UsageLedger.frontier_spend_usd_for_client()` now answers the question directly,
over `day` or `month`, priced per model like the global figure. No migration was
needed: `client_usage` already gained the model and token columns in #156.

Two behaviors changed beyond the isolation fix:

- **Monthly caps now do something.** Only the daily window was ever checked, so
  `--monthly-budget` was silently inert.
- **The 402 names what tripped.** The body carries `window`, `budget_usd`, and
  `spend_usd`, so a client can tell "I am out of budget" from "the org is out of
  budget" instead of inferring it.

The global caps still apply as an outer ceiling through the router's
`_frontier_budget_state()`, unchanged — a per-key allowance cannot be used to
exceed the org cap.

Covered by `tests/unit/test_virtual_key_budgets.py` (11 tests), including
two-key isolation and attribution for keys created without `--client-id`.

---

### Upstream retries and per-tier timeouts ([#159](https://github.com/naveenreddyalka/daari/issues/159))

Every upstream call got exactly one attempt, so a single transient 429, connection
reset, or 503 failed the request outright. Worse, the frontier pool advanced to
the next provider on *any* exception, spending a provider slot on a blip that a
200 ms backoff would have cleared.

`daari/router/retry.py` adds bounded exponential backoff with equal jitter, wired
into Ollama, MLX, and frontier calls. Three properties matter more than the
backoff itself:

- **Only transient failures retry.** 408, 429, 5xx, connect and read timeouts.
  A 401 or malformed body fails immediately, because retrying it only delays an
  error the caller has to see.
- **The retry budget never outlives the request timeout.** A backoff that would
  land past the deadline is not attempted, so retries cannot turn a slow request
  into a hung one.
- **Retries sit below the ledger write.** One client request stays one ledger
  row, so a flaky upstream cannot inflate request counts or spend.

`Retry-After` is honored when present, in both seconds and HTTP-date form, and
overrides the computed backoff. Jitter spreads retries from requests that failed
together, which otherwise return in lockstep and rebuild the load that caused the
failure.

Timeouts are now per-tier rather than a hardcoded 120s: `upstream.local_timeout_seconds`
defaults to 120s (a cold local model is genuinely slow) and
`upstream.frontier_timeout_seconds` to 90s (a hosted API silent for 90s usually
stays silent).

Each retry becomes an `upstream_retry` trace step carrying the status and delay,
and increments `daari_upstream_retries_total`. A rising counter means backoff is
absorbing instability the client never saw.

Covered by `tests/unit/test_upstream_retry.py` (35 tests) and
`tests/unit/test_upstream_retry_wiring.py` (14 tests).

---

### Test isolation: a flake and a hazard

`tests/integration/test_redis_l1_gateway.py` failed roughly one run in ten while
passing in isolation. Two independent causes, found by reproducing it rather than
by reading the test:

**The flake was `cache.l1.shadow_sample_rate`.** It ships at 0.05, so one in
twenty L1 hits spawns a background task that re-executes the request to audit the
cached answer. The test asserted its mock executor ran exactly once. Because the
audit runs as a task, whether it had incremented that counter by assertion time
was a race — the cache assertions always passed, which is why the failure surfaced
as a call count and looked unrelated to caching. The shared fixture now pins the
rate to 0; tests that exercise shadow sampling set it themselves, and the shipped
default is asserted separately so disabling it for tests cannot quietly disable it
for users.

**The hazard was `~/.daari`.** Six settings defaulted there, including the
command-context store that a locally running `daari serve` writes, its L1 cache,
and — worst — the real virtual-keys database. The suite was reading and writing a
live daemon's state, and a developer's actual credential store. `HOME` is now
redirected per test, which fixes the whole class rather than the six paths found
today.

Verified by 25 consecutive full-suite runs with no failures, against two failures
in the preceding 22. Guarded by `tests/unit/test_fixture_isolation.py` (8 tests),
which walks the settings tree and fails on any path escaping to the real home.

---

### Sampling parameters ([#161](https://github.com/naveenreddyalka/daari/issues/161))

`ChatCompletionRequest` declared six fields and set `extra="ignore"`, so `max_tokens`,
`top_p`, `stop`, `seed`, and `response_format` were accepted with a 200 and dropped.
A client asking for a bounded or deterministic answer got neither, and no error. The
other three surfaces were worse: the Anthropic endpoint parsed the `max_tokens` that
API *requires* and never used it, the Responses endpoint did the same with
`max_output_tokens`, and the Ollama facade read `temperature` out of `options` and
discarded `num_predict` beside it.

`daari/gateway/sampling.py` now owns one `SamplingParams` model with a reader per
surface, and each executor maps it on the way out. Three rules shaped it:

- **Unset means absent.** Sending `None` for an omitted parameter would override the
  backend's own default, so unset keys never reach a payload.
- **What cannot be honored is reported.** `presence_penalty`, `n > 1`, `logprobs`, and
  `tool_choice: required` become a `daari_meta.warning`. Appended, not assigned: a
  low-confidence answer already sets a warning, and that is when a client most needs
  to know what else was dropped.
- **Only honored parameters split the cache.** Sampling is in the cache key, so a
  16-token answer cannot be served to a request asking for 500, while a parameter that
  never reached the model does not fragment the cache. Requests that set nothing keep
  hitting pre-#161 entries.

Two bugs the mocked tests could not have found, both caught by asserting on the wire:
`max_completion_tokens` is present-but-`None` in a parsed body, so `get(key, default)`
read the `None` and never fell back to `max_tokens`; and Ollama matches `stop`
case-sensitively, which broke a test rather than the mapping.

Covered by `tests/unit/test_sampling_params.py` (mapping), `test_sampling_end_to_end.py`
(values reach the wire, across all four surfaces), and `tests/integration/test_sampling_live.py`,
which confirms against a real `llama3.2:3b` that the cap truncates, a shared seed
reproduces, a stop sequence ends generation, and JSON mode parses.

---

### PyPI and Homebrew ([#160](https://github.com/naveenreddyalka/daari/issues/160))

v1.1.1, v1.1.2, and v1.2.0 all built and then failed `invalid-publisher` because
no trusted publisher was registered. That is one form under a PyPI account — no
API, no token — so it waited on a human. On 2026-08-13 the pending publisher was
added with the OIDC claims `publish.yml` sends, and
`python scripts/release_pypi.py publish --target pypi` reran the failed job from
the `v1.2.0` tag so the upload matched the tag rather than `main`.
`verify --version 1.2.0` then installed into a throwaway venv and ran
`daari --help`. The Homebrew formula and tap were already filled from the earlier
prep; the `formula` job in `publish.yml` did not run on the rerun because it was
added after the tag, and had nothing left to write.

---

### Multimodal images ([#164](https://github.com/naveenreddyalka/daari/issues/164))

`content_to_text` kept only text blocks, so an `image_url` part was accepted with
a 200 and the model answered as if no picture was sent. The capability check then
looked for the substring `"image_url"` in that already-flattened text, so `vision`
could never fire.

Images now live on `Message.images`. Ollama gets them as `images: [b64]`; OpenAI-
compatible backends get `image_url` content parts. A stack with no vision-capable
model returns 422 rather than a confident wrong answer. Cache keys hash the image
bytes; a request with no images keeps its pre-#164 key.

### Embeddings endpoint ([#163](https://github.com/naveenreddyalka/daari/issues/163))

`OllamaEmbedder` already ran in-process for L1, but there was no `POST /v1/embeddings`,
so any app that wanted a vector had to point at a second host. The endpoint is
OpenAI-shaped (string or batch), served by `cache.l1.embedding_model`, cached in L0
under an `__embed__:` key, listed on `/v1/models`, and recorded as tier `embed`.
`model: daari` aliases the configured embedder; anything else is 400.

### Native Anthropic L6 egress ([#166](https://github.com/naveenreddyalka/daari/issues/166))

`provider: anthropic` used to POST an OpenAI-shaped body at `/chat/completions` and
sprinkle `cache_control` on system strings. That is not the Anthropic API, so
Claude keys 400'd and prompt-cache billing never applied. `FrontierExecutor` now
selects a native Messages path when `provider` is `anthropic`/`claude` or
`anthropic.com` is in `base_url`: `x-api-key` + `anthropic-version: 2023-06-01`,
system text in the top-level `system` field, `tool_use`/`tool_result` blocks,
image sources, and `cache_control: ephemeral` on the last system block. Stream
deltas parse `content_block_delta` / `text_delta`. OpenAI-compatible providers
are unchanged.

Ingress gained `POST /v1/messages/count_tokens` — a local `estimate_tokens` of
system + messages + tools, not an L6 call. Claude-family clients use it for
context budgeting.

Covered by `tests/unit/test_anthropic_egress.py` and
`tests/integration/test_anthropic_egress_live.py` (skipped without
`ANTHROPIC_API_KEY`).

### MCP JSON-RPC server ([#162](https://github.com/naveenreddyalka/daari/issues/162))

`POST /v1/mcp/query` was a bespoke body, not JSON-RPC, so no real MCP client could
connect even though the README claimed `tools/list` / `tools/call`. `POST /mcp` is
now a streamable-HTTP JSON-RPC 2.0 endpoint: `initialize`, `notifications/*` (202),
`tools/list`, `tools/call`, with parse/invalid/method-not-found codes. Tools are
`route`, `stats`, and registered `integration:` / `mcp:` providers, each with an
`inputSchema`. Auth is the existing master / virtual-key middleware. The old query
path stays as a deprecated alias (`Deprecation: true`, `Link: </mcp>`).

Covered by `tests/unit/test_mcp_server.py`. Client config:
[MCP guide](developer/guides/clients/mcp.md).

### Responses API completeness ([#165](https://github.com/naveenreddyalka/daari/issues/165))

The adapter was text-only: `function_call` input items were skipped, tool-call
output items were never emitted, and there was no conversation state. Agent
frameworks moving off Assistants (sunset 2026-08-26) could not use this surface.

`function_call` / `function_call_output` now map to internal `tool_calls` /
`role=tool`. Non-stream output emits `function_call` items; streams emit
`response.function_call_arguments.delta`. `previous_response_id` prepends the
stored conversation (sqlite next to the trace store). `store: false` skips
persistence. `background: true` returns `queued` and `GET /v1/responses/{id}`
polls to `completed`. `include` is 400; `metadata` is echoed.

Covered by `tests/integration/test_responses_api.py`, including a call through
the official OpenAI `AsyncOpenAI.responses` client.

### Distributed rate limiting ([#169](https://github.com/naveenreddyalka/daari/issues/169))

Virtual-key RPM used to be a SQLite `INSERT` + `COUNT` on every request — no TPM,
no global cap, no concurrency gate, and no shared counters across replicas. One
runaway agent loop could saturate the local GPU.

`daari/auth/rate_limit.py` now owns one limiter with Redis counters when
`cache.backend: redis` and SQLite otherwise. RPM and TPM apply per key and per
model (`rate_limit.rpm` / `tpm` / `model_rpm` / `model_tpm`; a virtual key's
`--rpm` / `--tpm` override the defaults). `max_in_flight` plus `queue_size`
bounds concurrency; overflow is 503 + `Retry-After`. Successful and rejected
responses carry `X-RateLimit-Limit` / `Remaining` / `Reset`. `/metrics` exposes
the configured limits and current in-flight / queued gauges. The Redis path
never opens SQLite.

Covered by `tests/unit/test_rate_limit.py`.

### Local backend pool ([#170](https://github.com/naveenreddyalka/daari/issues/170))

Local tiers accepted one Ollama URL. A dead or overloaded host failed every
request until restart — no health checks, no load balancing, and circuit
breakers existed only for frontier providers.

`routing.local_pool.backends` is a per-tier host list (empty still means
`ollama.base_url`). A background loop probes `/api/version` (or MLX
`/v1/models`) without blocking requests. Pick is `least_outstanding` or
`round_robin`, with warm-model hosts preferred. Each host has a
`CircuitBreaker`. `/ready` is `ready`, `degraded` (200, some hosts down), or
`not_ready` (503). The chosen host is `daari_meta.backend_id`, a `backend_pick`
trace step, and `daari_backend_*` Prometheus series. All hosts down is a typed
`backend_unavailable` 503.

Covered by `tests/unit/test_local_pool.py`.

### Redis L1 lost-update ([#150](https://github.com/naveenreddyalka/daari/issues/150))

`RedisSemanticCache` stored the whole entry list under one key and did an
unsynchronized GET/SET. Two replicas that loaded the same list each appended
and the later SET dropped the earlier write — the opposite of sharing
nearest-neighbor hits.

Puts (and TTL prune) now go through `WATCH`/`MULTI` optimistic locking with
five retries, then a last-snapshot write that never raises into the request
path. `max_entries` eviction still applies to the merged list. No new
dependency.

Covered by `tests/unit/test_redis_semantic.py`.

### OTel GenAI semantic conventions ([#167](https://github.com/naveenreddyalka/daari/issues/167))

OTel export used to emit ad-hoc `daari.*` attributes with everything
stringified — no `gen_ai.*` names, so daari traces joined nothing in
Langfuse/Grafana/Datadog.

Root spans are now `chat {model}` with `gen_ai.operation.name`, `provider.name`,
`request.model`, `response.model`, `response.finish_reasons`, `usage.*` (real
provider counts only — estimates are flagged `daari.usage_estimated`, never
reported as measurements), and `error.type`. Metrics:
`gen_ai.client.token.usage`, `gen_ai.client.operation.duration`, and for
streams `gen_ai.server.time_to_first_token` / `time_per_output_token`.
daari facts stay under `daari.*`; numbers are numbers. Startup installs OTLP
providers when `OTEL_EXPORTER_OTLP_ENDPOINT` is set and nothing configured
OTel first. Conventions are Development status and may shift.

Covered by `tests/unit/test_otel_genai.py`; wire-verified by
`scripts/smoke_otel_genai.py` against an in-process OTLP collector.

### Live product benchmark ([#189](https://github.com/naveenreddyalka/daari/issues/189))

`scripts/bench.sh` was a curl smoke with UUID prompts — it could not back a
routing or cache-trust claim. `scripts/bench_live.py` now runs the labeled
corpora (`evals/routing/prompts.jsonl`, `evals/cache/verification.jsonl`)
against a hermetic `daari serve` + real Ollama (fresh cold-cache instance per
phase), reports $0-tier rate, routing accuracy, L1 paraphrase retention /
near-miss rejection, p50/p95 per tier, and frontier USD avoided from
provider-reported tokens, and publishes
[developer/resources/benchmarks.md](developer/resources/benchmarks.md) with
commit, hardware, model IDs, and date. Never calls a paid API by default
(`X-Daari-No-Frontier`; expected-L6 rows excluded unless `--allow-frontier`).
Reproduce guide:
[developer/guides/observability/live-benchmark.md](developer/guides/observability/live-benchmark.md).

First honest run found a real trust bug: the #168 lexical verifier is bypassed
on the serve path (router calls `nearest()`, never `get()`), so near-misses
serve from L1 — filed as
[#206](https://github.com/naveenreddyalka/daari/issues/206) (P1).

Pure logic covered by `tests/unit/test_bench_live.py`; the live path runs via
`pytest -m benchmark` or the script itself, skipping cleanly without Ollama.

### L1 verifier restored on the serve path ([#206](https://github.com/naveenreddyalka/daari/issues/206))

The #168 lexical verifier only ran inside `SemanticCache.get()`, but the
draft-band refactor (`779a146`) had switched the router to `nearest()` — so no
live request was ever verified and near-misses served from cache ("15% of 300"
got the answer for "15% of 200"). `nearest_with_source()` now returns the
stored prompt text and both serve paths (non-streaming and streaming) apply
`verify_for_serving()` before serving; a vetoed hit falls back to the draft
band instead. Live bench: near-miss rejection 17% → 100%; retention dips to
61% because the verifier vetoes benign synonym substitutions — recall
follow-up filed as
[#208](https://github.com/naveenreddyalka/daari/issues/208).

Covered by `tests/unit/test_l1_verify_serve_path.py` (router-level, both
paths, veto + paraphrase + draft fallback + avoided-counter).

### Competitive comparison bench ([#190](https://github.com/naveenreddyalka/daari/issues/190))

`scripts/bench_compare.py` answers "why daari" with the #189 corpus run three
ways on the same machine: raw Ollama, daari with caches (hermetic cold
daemon), daari with `X-Daari-No-Cache`. Publishes
[developer/resources/benchmark-comparison.md](developer/resources/benchmark-comparison.md)
(linked from the benchmarks page and mkdocs nav) with per-prompt latency,
tier, implied frontier USD (gpt-4o rates priced onto recorded tokens — never
billed), and aggregates: median cache-hit speedup, total USD avoided, $0-tier
rate. Prompt IDs match #189 so rows join. Default run never calls a paid API;
`--live-frontier` exists but is not required to publish.

Pure logic covered by `tests/unit/test_bench_compare.py`; live path via
`pytest -m benchmark` or the script, skipping cleanly without Ollama.

### Client-path live E2E pack ([#191](https://github.com/naveenreddyalka/daari/issues/191))

`tests/integration/test_client_path_live.py` exercises the surfaces an IDE
client actually sends against real Ollama: OpenAI streaming and Anthropic
`/v1/messages` streaming each yield more than one chunk; a vision request on
a text-only stack returns 422; `POST /v1/embeddings` returns a vector whose
length matches the embedder (`nomic-embed-text`). Sampling (`max_tokens`
binds, seed reproduces) stays in `test_sampling_live.py`. The color-conditioned
vision check skips unless a vision-capable model is pulled. Default suite
stays green (`@pytest.mark.integration`).

Note: stock capability defaults tag L5 as `vision` even when L5 is collapsed
onto a text-only 3B — the live 422 test declares the catalog explicitly.

### daari vs LiteLLM ([#214](https://github.com/naveenreddyalka/daari/issues/214))

`scripts/bench_vs_litellm.py` runs the #189 routing corpus through a default
LiteLLM OpenAI-compat proxy (same Ollama, no paid providers) and a hermetic
`daari serve`. Publishes
[developer/resources/benchmark-vs-litellm.md](developer/resources/benchmark-vs-litellm.md)
joined by prompt ID. LiteLLM is not a runtime dependency: skip without it, or
`--spawn` into a throwaway venv. Covered by `tests/unit/test_bench_vs_litellm.py`.

### Load harness ([#215](https://github.com/naveenreddyalka/daari/issues/215))

`scripts/bench_load.py` measures achieved RPS and p50/p95 on a hermetic
`daari serve`: a warmed L0 replay mix and a unique no-cache generate mix
(`max_tokens` capped). Publishes
[developer/resources/benchmark-load.md](developer/resources/benchmark-load.md)
with commit, hardware, concurrency, RPS, p95, and errors. No vegeta/k6
dependency. Capacity guide now points at the measured page. Covered by
`tests/unit/test_bench_load.py` (reporter + skip).

### OIDC ES256 JWKS ([#151](https://github.com/naveenreddyalka/daari/issues/151))

`verify_oidc_token` dispatches on JWK `kty` (`RSA` → RS256/384/512, `EC` →
ES256/384/512). Unsupported `kty` raises `ValueError` naming the type. JWKS
documents that mix `use: enc` and `use: sig` prefer the signing key. Covered
by `tests/unit/test_oidc_jwks.py`.

### Settings validate_assignment ([#152](https://github.com/naveenreddyalka/daari/issues/152))

Runtime-mutated settings models (`RoutingSettings`, `FrontierSettings`,
`CacheSettings` + L0/L1, `BoundariesSettings`, `ObservabilitySettings`) use
`validate_assignment` and field constraints (`ge`/`le`, `Literal` modes).
`setattr` of an out-of-range value raises `ValidationError`. Config PATCH
still returns 400 via `daari/config/validate.py`.

---

## How to update

1. Mark tasks `[x]` when merged to `main`; add commit hash in **Notes** when helpful.
2. Refresh **Last updated** and pytest count after test changes.
3. Do not mark done without implementation — check `daari/cli/`, `tests/`, and `git log`.
4. Keep Phase B+ as preview; detail stays in [ROADMAP](prd/ROADMAP.md) and [phase-a.md](plans/phase-a.md). Forward work: [ROADMAP-v2](prd/ROADMAP-v2.md).
