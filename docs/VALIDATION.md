# daari — Validation Summary

> Date: 2026-06-21  
> Scope: Phase C3 integration depth + hardening slice

## Feature checklist vs PRD

| Feature set | Status | Notes |
|-------------|--------|-------|
| L2 rules engine | ✅ implemented | Deterministic JSON/YAML transforms before model tiers |
| L2-dev developer command rules | ✅ implemented | Regex detection for git/test/lint/readonly command-context prompts |
| CCS command context store | ✅ implemented | Disk-backed command output cache with TTL reads before re-run |
| Lt B.0 dispatch | ✅ implemented | `git status`, `git diff`, `pytest`, `eslint` execution via subprocess |
| PolicyEngine B.0 | ✅ implemented | allow/block/unknown(deny or ask) decisions before Lt |
| L4 medium local tier | ✅ implemented | L3→L4→L6 escalation path (L4 fallback to L3 when unavailable) |
| L5 local-large tier wiring | ✅ implemented (scaffold) | L3→L4→L5→L6 chain, model/config/provider wiring, optional pull only |
| Model routing preferences | ✅ implemented | `routing.prefer` + `models.weights` config shape and tier picker usage |
| `--no-frontier` / no-frontier header | ✅ implemented | CLI flag + `X-Daari-No-Frontier` request override |
| Streaming SSE | ✅ implemented (enriched) | stream chunks now include `daari_meta` tier/provider/model |
| Wizard polish | ✅ implemented | frontier key helper + openai-compat setup flow added |
| `daari install` Typer parity | ✅ implemented (minimal) | CLI wrapper to run `scripts/install.sh` with doctor option |
| Eval GP-11–GP-20 | ✅ implemented | prompts expanded and regression assertions updated |
| ProviderRegistry router wiring | ✅ implemented (minimum) | model executors registered and resolved through registry |
| Integration providers (C3) | ✅ implemented | Sourcegraph GraphQL + GHE repo/issue REST search with token-gated fallback |
| Anthropic gateway adapter | ✅ implemented (minimal) | `/v1/messages` non-streaming route mapped to internal router |
| MCP gateway ingress | ✅ expanded | `/v1/mcp/query` now supports `tools/list` + `tools/call` and tool JSON schemas |
| `daari setup openai-compat` | ✅ implemented | prints OPENAI_* exports + writes `~/.daari/.env.example` |
| `daari context clear` | ✅ implemented | clears L0/L1/CCS caches via CLI |
| `daari setup all` | ✅ implemented | runs setup recipes for detected clients |
| `daari setup intellij` | ✅ implemented (minimal) | dry-run/apply/undo with helper config file + docs |
| `daari setup vscode` | ✅ implemented (minimal) | dry-run/apply/undo with VS Code settings marker |
| `daari setup claude-code` | ✅ implemented (minimal) | writes OPENAI_* env helper + config pointer file |
| Lt ask/confirm UX | ✅ implemented | `daari_meta.confirmation_prompt` + `X-Daari-Confirm: yes` + `--yes` prompt support |
| L2-live URL fetch | ✅ implemented (minimal) | fetch/read/summarize URL trigger using httpx + L3 summary |
| Doctor L4 pull hint | ✅ implemented | optional `model_l4` check with `ollama pull` hint |
| Doctor L5 pull hint | ✅ implemented | optional `model_l5` check with `ollama pull` hint |
| Install optional L4/L5 pulls | ✅ implemented | `daari install --pull-l4 --pull-l5` env passthrough to script |
| Anthropic streaming | ✅ implemented | `/v1/messages` now supports `stream: true` SSE event protocol |
| Anthropic stream fallback | ✅ implemented | stream errors now emit `event:error` and fall back to non-stream SSE response |
| Browser extension scaffold | ✅ implemented | `packages/browser-extension` README + manifest placeholder |
| Web UI scaffold | ✅ implemented | `packages/web-ui/README.md` placeholder scaffold added |
| Per-project profiles | ✅ implemented | `~/.daari/profiles/<hash|slug>.yaml` + `DAARI_PROFILE` merge support |
| Skills loader stub | ✅ implemented | `~/.daari/skills/*.md` merged into model system prompt prefix |
| Enterprise scaffold | ✅ implemented (minimal) | `daari/enterprise/OrgSettings` pydantic model scaffold |

## Verification results

- `.venv/bin/python -m pytest -m "not integration and not benchmark"`: **92 passed, 2 deselected**
- `OLLAMA_HOST=http://127.0.0.1:11434 .venv/bin/python -m pytest -v`: **94 passed**
- `.venv/bin/python -m pytest -m benchmark`: **1 passed, 93 deselected**
- `./scripts/demo.sh`: **pass**
- `./scripts/bench.sh`: **pass**
- Manual smoke (temporary daemon on :11535 + integration tests):
  - `tools/list`: pass (`5` tools returned with schemas)
  - `tools/call`: pass (`route` invocation returns structured result)
  - `@sourcegraph` trigger: pass (`provider_id=integration:sourcegraph`, token-missing warning without env token)
  - `@ghe` trigger: pass (`provider_id=integration:ghe`, token-missing warning without env token)
  - Anthropic stream (`/v1/messages`, `stream: true`): pass (`message_start`/`message_stop` present)
  - Profile merge: pass (`DAARI_PROFILE=smoke` merged `routing.prefer=accuracy`)

## Performance summary

Measured on local machine against a clean daemon instance (`scripts/bench.sh` + targeted probes):

| Tier/path | Observed p50 latency |
|-----------|----------------------|
| L0 exact cache | ~33.7 ms (observed tier: `L1` in this run) |
| L1 semantic cache | ~46.6 ms |
| L2 rules | ~31.5 ms |
| Lt command (`git status`) | ~61.2 ms |
| L3 local model | ~816.2 ms |
| L4/L5 override paths | covered by tests; runtime depends on local model availability |

## Benefits vs alternatives

| Option | Strengths | Tradeoffs | User benefit vs option |
|--------|-----------|-----------|------------------------|
| Cursor-only cloud model routing | Great UX, no local setup | Every request tends to be cloud-cost/latency sensitive | daari adds local cost control and policy-driven tool execution |
| Raw Ollama | Fully local model inference | No built-in request-tier routing, rules, Lt tooling, or CCS | daari adds tiered cache/rules/tool orchestration on top of Ollama |
| LiteLLM / cloud proxy stacks | Multi-provider API normalization | Primarily proxying models, weaker local non-LLM execution path | daari prioritizes local-first execution and $0 tiers before cloud |
| DIY scripts + shell aliases | Flexible for power users | Fragmented, no unified API surface for IDE/agents | daari gives one endpoint + consistent routing metadata and policy |

## Known gaps / issues

| Severity | Gap | Impact | Next action |
|----------|-----|--------|-------------|
| Medium | L4 model not auto-installed; can fallback to L3 | Reduced quality path unless user pulls L4 model | Keep doctor/model hints; consider optional auto-pull |
| Medium | Sourcegraph/GHE live queries require user tokens | Integration calls degrade to skip messages without env tokens | Document env setup and add setup helper in follow-up |
| Medium | L6 manual smoke requires configured API key | Cannot validate live frontier path in keyless env | Add optional key-aware smoke script path |
| Low | Anthropic stream runtime requires Ollama chat endpoint | stream can emit error event if local model endpoint unavailable | Improve preflight health check and fallback messaging |
| Low | Wizard is still single-choice flow | Slight setup friction for first-time setup | Expand wizard to multi-step/multi-select in follow-up |

