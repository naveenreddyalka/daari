# Changelog

All notable changes to daari. Format loosely follows [Keep a Changelog](https://keepachangelog.com); versions follow [SemVer](https://semver.org). Full detail per release lives in `docs/RELEASE-v*.md`; per-task history in [docs/TRACKING.md](docs/TRACKING.md).

## [Unreleased]

### License

- Relicensed the tree back to [Apache 2.0](LICENSE) ([#227](https://github.com/naveenreddyalka/daari/issues/227), [ADR-0016](docs/adr/0016-apache-2-relicense.md)). v1.3.0 as tagged remains PolyForm NC.

## [1.3.0] — 2026-08-17 · [notes](docs/RELEASE-v1.3.0.md)

**Gateway completeness, hardening & relicense** — 51 commits: full agent surface (Responses, MCP, embeddings, vision), distributed rate limits, health-checked local backend pool, real token accounting, and a move to PolyForm Noncommercial 1.0.0.

### License change

- **Relicensed from Apache 2.0 to PolyForm Noncommercial 1.0.0** (#202): then-current `LICENSE` was NC; commercial use required a separate license. Releases through v1.2.0 remain Apache 2.0. Later reversed on `main` by #227.

### Gateway surface completion

- **Responses API completed for agents** (#196): background mode, `previous_response_id` chaining, response store, streaming events
- **Real MCP JSON-RPC server at `POST /mcp`** (#195): tools/list, tools/call over the gateway
- **`POST /v1/embeddings`** on the OpenAI surface (#193)
- **Vision requests keep image parts** (#192); OpenAI sampling parameters honored instead of dropped (#187)
- **Native Anthropic `/v1/messages` L6 egress** (#194): no more lossy OpenAI-format round-trip for Claude

### Reliability & scale-out

- **Distributed rate limiting** (#197 / issue #169): RPM + TPM per key and per model with Redis or SQLite counters, global in-flight cap with bounded queue, `X-RateLimit-*` headers, limits in `/metrics`
- **Health-checked local backend pool** (#198 / issue #170): multiple Ollama/MLX hosts per tier, background health probes, least-outstanding/round-robin pick, per-host circuit breakers, degraded `/ready`
- **Redis L1 lost-update fix** (#199 / issue #150): `WATCH`/`MULTI` optimistic locking preserves concurrent replica writes
- **Transient upstream retries with bounded backoff** (#185); streams enforce boundaries, guardrails, and L6 escalation (#175); deterministic tiers and frontier SSE relay on streams (#177)

### Correctness & accounting

- **Real token accounting** (#178): provider-reported token counts and per-model, per-direction pricing
- **L1 semantic hits verified before serving** (#179); virtual-key budgets charged to the key that spent them (#184)
- Test isolation from the real `~/.daari` and Redis L1 flake fix (#186)

### Packaging & release

- PyPI packaging unblocked; generated Homebrew formula (#182), guided PyPI publish runner (#183) — `daari==1.2.0` went live on PyPI

### Developer documentation overhaul

- New public docs tree under `docs/developer/` (Get started, Concepts, Guides, Tutorials, Reference, Internals, Resources)
- MkDocs nav demotes TRACKING/AUTOMATION; generated API/config via `scripts/gen_reference.py` → `docs/developer/reference/`
- Pitch/demo: `docs/developer/resources/pitch-outline.md`, `docs/pitch/DEMO.md`
- Legacy `docs/setup/*` pages redirect into the new guides

### Product boundaries / scope gate (Roadmap F6)

- Configurable `boundaries.*` (off by default): product description, allow/deny topics, examples, `mode: warn|block`
- Local B0 classify + B1 judge; clear out → `tier=boundary` with zero model tokens
- Config editor GET/PATCH + persist; org policy sync; example `examples/boundaries/fintech-assist.yaml`
- Smoke: `scripts/smoke_boundaries.py` · ADR-0015 · Fable tags in [docs/REVIEW-TAGS.md](docs/REVIEW-TAGS.md)
- Triple-verified: unit (`test_boundaries`) + integration (`test_boundaries_gateway`) + live smoke

### Roadmap v2 (F1–F5) — merged to main 2026-07-24

- **F1:** Docker/compose + `/ready`, MkDocs site, PyPI prep + benchmarks doc (upload still user-gated), Homebrew formula stub
- **F2:** Responses API, L6 frontier pool (fallback / key rotation / circuit breakers), guardrails, virtual keys, capability catalog + `--suggest-models`
- **F3:** Prometheus `/metrics` + Grafana JSON, optional OTel export, structured stdout logs, config editor API
- **F4:** Redis L0, Postgres ledger/traces, Helm chart, org inference pool, `daari enterprise bootstrap` / policy-sync, SSO/RBAC/audit tracers
- **F5:** Live-source providers, MCP egress, Phase B metrics script, Homebrew docs

### Auto-mode deepeners (2026-07-24) — needs stronger-model review

- Periodic in-daemon org policy sync when `enterprise.policy_sync_url` is set
- Config editor `persist: true` writes safe subset to `~/.daari/config.yaml`
- `daari learn propose-defaults` (D4 proposal YAML only — never auto-promotes)
- Web UI config editor card (confidence / prefer / daily budget)
- Handoff notes: [docs/HANDOFF-AUTO-2026-07.md](docs/HANDOFF-AUTO-2026-07.md)

### Redis L1 shared cache (issue #135)

- `cache.backend=redis` now covers L1 as well as L0 (`RedisSemanticCache`, `redis_l1_prefix`)
- Triple-verified: unit + gateway integration + `scripts/smoke_redis_l1.py`
- Fable re-verify tags: see [docs/REVIEW-TAGS.md](docs/REVIEW-TAGS.md)

### Redis + Postgres backends E2E (issue #142)

- Compose profile `backends` (redis + postgres); offline smoke with fakes; live via `scripts/smoke_backends.sh`
- Fable tags: `fable-review/142-*` — see [docs/REVIEW-TAGS.md](docs/REVIEW-TAGS.md)

### Web UI API key / Bearer (issue #141)

- Toolbar field stores token in `localStorage` and sends `Authorization: Bearer` on all dashboard + config-editor fetches
- Triple-verified: `packages/web-ui` npm tests + config editor unit + `scripts/smoke_webui_auth.py`
- Fable tags: `fable-review/141-*` — see [docs/REVIEW-TAGS.md](docs/REVIEW-TAGS.md)

### OIDC JWKS admin SSO (issue #136)

- `verify_oidc_token` / `verify_access_token` (JWKS or HMAC stub); optional `daari[oidc]`
- `POST /v1/daari/sso/session` can mint a virtual key on first login
- Gateway middleware accepts verified SSO bearers alongside API keys
- Triple-verified + tags `fable-review/136-*`

### Earlier Unreleased (pre-v2)

- Anthropic stream observability: `error_type` on failures, `anthropic_stream_done` event, profile-driven latency step-down parity with the OpenAI path (#101, #102)
- Phase D3: `daari learn export-stats` — opt-in, review-first anonymized stats export with sensitive-key guard (#102)
- `daari learn deploy`: serve fine-tuned adapters via `mlx_lm.server` or fuse to GGUF + `ollama create` (#102)
- Roadmap v2 (`docs/prd/ROADMAP-v2.md`): OSS launch pack, gateway parity, Prometheus/OTel, enterprise scale-out; docs refresh + community files

## [1.2.0] — 2026-07-23 · [notes](docs/RELEASE-v1.2.0.md)

**Learning, Trust & Clients** — 26 commits across four programs, live-E2E validated.

- **Phase D learning:** implicit outcome capture + explicit feedback (`daari feedback`), `daari learn stats/recommend`, opt-in routing tuner, opt-in example capture → `daari learn export-dataset` → `daari learn finetune` (MLX LoRA)
- **Trust trains:** L1 input normalization, response-diversity monitor, shadow-sampled **false-hit rate**; Anthropic prompt-cache passthrough, conversation compaction, frontier compression; `daari profile` + latency budgets + warm-model preference; learned router (`daari learn train-router`); monthly soft/hard budgets, per-client attribution, pre-frontier PII scrub
- **Clients:** one-click Claude Code (`~/.claude/settings.json` merge, full Anthropic tool passthrough), Ollama-compatible facade (`/api/*`) for JetBrains AI Assistant, Cursor tunnel setup with auto-generated gateway API-key auth, per-project `.daari.yaml` profiles (`X-Daari-Project`)
- **Platform:** MLX backend (`mlx_lm.server`) as optional L3–L5 executor, dynamic Ollama `num_ctx`, tool-argument normalization, trailing-system-message hoist fix for Claude Code (#94), request-log rotation, embedding memoization, web UI usage/savings/traces dashboard, CI ruff pin

## [1.1.2] — 2026-07-11 · [notes](docs/RELEASE-v1.1.2-cursor-e2e.md)

- **Cursor BYOK E2E:** content-block normalization, Ask-mode tool stripping + history sanitization, streaming tier fallback (L4→L3), `/v1/models`, gateway request log — Cursor Ask verified end-to-end via cloudflared tunnel
- Streaming L1 semantic cache + draft injection parity; prompt profiling + category policies; request traces (`daari trace`); usage ledger + savings (`daari report`); frontier budget guard; context optimizer; tier caps
- Autonomous dev loop: `auto-dev` issue backlog, protected `main` with 4 CI checks, auto-merge, local watchdog with live E2E every 2h

## [1.1.1] — 2026-06-21 · [notes](docs/RELEASE-v1.1.1.md)

- L1 similarity threshold tuned to 0.88; deterministic bench script; doctor embedding-model check; PyPI publish workflow prep

## [1.1.0] — 2026-06-21 · [notes](docs/RELEASE-v1.1.md)

- Enterprise E2 org shared-cache service (`daari org-cache serve`, `L0-org`/`L1-org` + write-through) and E3 org learning (feedback ingestion, profile sync); web UI MVP dashboard

## [1.0.0] — 2026-06-21 · [notes](docs/RELEASE-v1.0.md)

- Initial release: local-first routing chain (L0 → CCS → L1 → L2/Lt → L3/L4/L5 → optional L6), OpenAI + Anthropic + MCP gateways, execution policy, setup recipes (Cursor/IntelliJ/VS Code/claude-code), doctor/install/demo tooling, Sourcegraph/GHE/GitLab providers, routing evals GP-01–GP-20

[Unreleased]: https://github.com/naveenreddyalka/daari/compare/v1.2.0...HEAD
[1.2.0]: https://github.com/naveenreddyalka/daari/compare/v1.1.2...v1.2.0
[1.1.2]: https://github.com/naveenreddyalka/daari/compare/v1.1.1...v1.1.2
[1.1.1]: https://github.com/naveenreddyalka/daari/compare/v1.1.0...v1.1.1
[1.1.0]: https://github.com/naveenreddyalka/daari/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/naveenreddyalka/daari/releases/tag/v1.0.0
