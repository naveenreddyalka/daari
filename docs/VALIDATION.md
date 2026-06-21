# daari — Validation Summary

> Date: 2026-06-20  
> Scope: v1.0 readiness + E2 tracer bullet (org shared-cache service/client)

## v1.0 readiness score

| Area | Status | Score |
|------|--------|-------|
| Core local-first routing (`L0`-`L6`, rules, CCS, Lt) | ✅ | 20 / 20 |
| Gateway compatibility (OpenAI, Anthropic, MCP) | ✅ | 15 / 15 |
| C3 integration providers (Sourcegraph, GHE, GitLab) | ✅ | 15 / 15 |
| Enterprise E1 + E2 runtime (org mode + shared cache service/client) | ✅ | 15 / 15 |
| Setup/install and operational commands | ✅ | 15 / 15 |
| Eval coverage GP-01–GP-20 | ✅ | 10 / 10 |
| Performance smoke and scripts (`demo`, `bench`) | ✅ | 10 / 10 |

**Overall readiness:** **100 / 100 (Ready for v1.0 tag)**.

## Verification results

- `.venv/bin/python -m pytest`: **114 passed, 1 skipped**
- `OLLAMA_HOST=http://127.0.0.1:11434 .venv/bin/python -m pytest -m integration`: **1 passed, 114 deselected**
- `.venv/bin/python -m pytest -m benchmark`: **1 passed, 114 deselected**
- `./scripts/demo.sh`: **pass**
- `./scripts/bench.sh`: **pass**

## Manual smoke (local)

- `@gitlab` trigger: **pass** (`provider_id=integration:gitlab`, token-missing warning when key absent)
- Org mode serve: **pass** (`daari serve --org acme --port 11535`, org cache root resolved and used)
- Org cache service: **pass** (`daari org-cache serve --org acme --port 11436`, `GET/PUT/stats` happy path + auth checks)
- Cross-instance shared cache hit: **pass** (instance A `L3` write-through, instance B `L0-org` hit for same prompt)
- MCP validation error path: **pass** (`tools/call` invalid schema input returns `MCP_ERR_SCHEMA_VALIDATION`)

## Performance summary

From `./scripts/bench.sh`:

| Tier/path | Observed p50 latency |
|-----------|----------------------|
| L3 local model | ~1209.7 ms |
| L0/L1 cache path | ~35-41 ms |
| L2 rules | ~40.6 ms |
| Lt command | ~57.0 ms |

## Deferred post-v1.0

| Severity | Gap | Impact |
|----------|-----|--------|
| Medium | Enterprise E3 collective learning/control plane | No org-wide learning feedback loop yet |
| Medium | Org L1 semantic matching in shared service | Current E2 tracer bullet uses key-based L1 reuse, not vector similarity search |
| Medium | Live CI smoke for tokenized C3 integrations | Requires org credentials not available in CI by default |
| Low | Web UI + browser extension | Currently scaffolds only |

