# daari — Task tracking

> Last updated: 2026-07-13  
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
