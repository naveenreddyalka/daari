# Changelog

All notable changes to daari. Format loosely follows [Keep a Changelog](https://keepachangelog.com); versions follow [SemVer](https://semver.org). Full detail per release lives in `docs/RELEASE-v*.md`; per-task history in [docs/TRACKING.md](docs/TRACKING.md).

## [Unreleased]

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
