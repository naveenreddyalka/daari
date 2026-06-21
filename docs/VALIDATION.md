# daari — Validation Summary

> Date: 2026-06-21  
> Scope: v1.1.1 continuation (enterprise profile sync hardening, browser extension options UX, web-ui export/theme, cursor setup smoke script)

## v1.0 readiness score

| Area | Status | Score |
|------|--------|-------|
| Core local-first routing (`L0`-`L6`, rules, CCS, Lt) | ✅ | 20 / 20 |
| Gateway compatibility (OpenAI, Anthropic, MCP) | ✅ | 15 / 15 |
| C3 integration providers (Sourcegraph, GHE, GitLab) | ✅ | 15 / 15 |
| Enterprise E1 + E2/E3 runtime (org mode + shared cache + learning feedback/profile sync) | ✅ | 15 / 15 |
| Setup/install and operational commands | ✅ | 15 / 15 |
| Eval coverage GP-01–GP-20 | ✅ | 10 / 10 |
| Performance smoke and scripts (`demo`, `bench`) | ✅ | 10 / 10 |

**Overall readiness:** **100 / 100 (Ready for v1.1.0 tag)**.

## Verification results

- `OLLAMA_HOST=http://127.0.0.1:11434 .venv/bin/python -m pytest`: **133 passed**
- `OLLAMA_HOST=http://127.0.0.1:11434 .venv/bin/python -m pytest -m integration`: **1 passed, 132 deselected**
- `.venv/bin/python -m pytest -m benchmark`: **1 passed, 132 deselected**
- `./scripts/demo.sh`: **pass**
- `./scripts/bench.sh`: **pass** (daemon-backed run)

## Manual smoke (local)

- `@gitlab` trigger: **pass** (`provider_id=integration:gitlab`, token-missing warning when key absent)
- `daari context clear`: **pass** (prints restart warning when daemon is active to avoid stale in-memory cache handles)
- `POST /v1/daari/reload-caches`: **pass** (refreshes in-memory cache handles on running daemon)
- `daari context clear` with daemon running: **pass** (invokes reload endpoint, falls back to restart note when reload fails)
- `daari doctor`: **pass** (now includes optional embedding-model check for `nomic-embed-text`)
- Org mode serve: **pass** (`daari serve --org acme --port 11535`, org cache root resolved and used)
- Org cache service: **pass** (`daari org-cache serve --org acme --port 11436`, `GET/PUT/stats` happy path + auth checks)
- Org learning service: **pass** (`POST /v1/org-learning/feedback`, `GET/PUT /v1/org-learning/profile`, admin token gate verified)
- Org-learning CLI: **pass** (`daari org-learning stats`, `daari org-learning export`, `daari org-learning sync`)
- Startup + periodic profile sync: **pass** (startup merge plus background polling via `org.learning_sync_seconds`)
- Manual feedback-to-profile check: **pass** (high-latency feedback flipped profile `prefer` to `latency`, router consumed merged profile)
- Cross-instance shared cache hit: **pass** (instance A `L3` write-through, instance B `L0-org` hit for same prompt)
- MCP validation error path: **pass** (`tools/call` invalid schema input returns `MCP_ERR_SCHEMA_VALIDATION`)
- Web UI serve + index route: **pass** (`daari web-ui serve`, dashboard returns HTTP 200; auto-refresh, export JSON, and theme toggle rendered)
- Browser extension runtime assets: **pass** (MV3 manifest + popup + options page assets loadable from `packages/browser-extension/`)
- Cursor setup smoke script: **pass** (`./scripts/smoke-cursor-dry-run.sh`)

## Performance summary

From `./scripts/bench.sh`:

| Tier/path | Observed p50 latency |
|-----------|----------------------|
| L3 local model | ~865.9 ms |
| L0/L1 cache path | ~278-831 ms (environment resolved to L3 in this run) |
| L2 rules | ~52.3 ms |
| Lt command | ~60.6 ms |

## Deferred post-v1.0

| Severity | Gap | Impact |
|----------|-----|--------|
| Medium | Org L1 semantic matching in shared service | Current E2 tracer bullet uses key-based L1 reuse, not vector similarity search |
| Medium | Live CI smoke for tokenized C3 integrations | Requires org credentials not available in CI by default |
| Low | Browser extension end-to-end UI tests | Runtime works locally, but automated browser-level tests are still pending |

