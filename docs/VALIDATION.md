# daari — Validation Summary

> Date: 2026-06-21  
> Scope: v1.0 readiness (C3 GitLab parity + E1 org runtime scaffold + MCP validation)

## v1.0 readiness score

| Area | Status | Score |
|------|--------|-------|
| Core local-first routing (`L0`-`L6`, rules, CCS, Lt) | ✅ | 20 / 20 |
| Gateway compatibility (OpenAI, Anthropic, MCP) | ✅ | 15 / 15 |
| C3 integration providers (Sourcegraph, GHE, GitLab) | ✅ | 15 / 15 |
| Enterprise E1 runtime scaffold (org mode, org cache paths, doctor) | ✅ | 15 / 15 |
| Setup/install and operational commands | ✅ | 15 / 15 |
| Eval coverage GP-01–GP-20 | ✅ | 10 / 10 |
| Performance smoke and scripts (`demo`, `bench`) | ✅ | 10 / 10 |

**Overall readiness:** **100 / 100 (Ready for v1.0 tag)**.

## Verification results

- `.venv/bin/python -m pytest`: **103 passed, 1 skipped**
- `OLLAMA_HOST=http://127.0.0.1:11434 .venv/bin/python -m pytest -m integration`: **1 passed, 103 deselected**
- `.venv/bin/python -m pytest -m benchmark`: **1 passed, 103 deselected**
- `./scripts/demo.sh`: **pass**
- `./scripts/bench.sh`: **pass**

## Manual smoke (local)

- `@gitlab` trigger: **pass** (`provider_id=integration:gitlab`, token-missing warning when key absent)
- Org mode serve: **pass** (`daari serve --org acme --port 11535`, org cache root resolved and used)
- MCP validation error path: **pass** (`tools/call` invalid schema input returns `MCP_ERR_SCHEMA_VALIDATION`)

## Performance summary

From `./scripts/bench.sh`:

| Tier/path | Observed p50 latency |
|-----------|----------------------|
| L3 local model | ~1096.9 ms |
| L0/L1 cache path | ~40-70 ms |
| L2 rules | ~42.6 ms |
| Lt command | ~67.5 ms |

## Deferred post-v1.0

| Severity | Gap | Impact |
|----------|-----|--------|
| Medium | Enterprise E2 shared org cache service | No remote org cache sync yet; E1 uses local org-scoped paths |
| Medium | Enterprise E3 collective learning/control plane | No org-wide learning feedback loop yet |
| Medium | Live CI smoke for tokenized C3 integrations | Requires org credentials not available in CI by default |
| Low | Web UI + browser extension | Currently scaffolds only |

