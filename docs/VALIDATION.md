# daari — Validation Summary

> Date: 2026-06-20  
> Scope: Phase B completion + Phase C bootstrap slice

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
| Integration providers scaffold | ✅ implemented (scaffold) | Sourcegraph/GHE deferred providers registered as placeholders |
| Anthropic gateway adapter | ✅ implemented (minimal) | `/v1/messages` non-streaming route mapped to internal router |
| MCP gateway stub | ✅ implemented (stub) | `/v1/mcp/query` explicit `501` for deferred Phase C1 implementation |
| `daari setup openai-compat` | ✅ implemented | prints OPENAI_* exports + writes `~/.daari/.env.example` |
| `daari context clear` | ✅ implemented | clears L0/L1/CCS caches via CLI |
| Doctor L4 pull hint | ✅ implemented | optional `model_l4` check with `ollama pull` hint |
| Doctor L5 pull hint | ✅ implemented | optional `model_l5` check with `ollama pull` hint |
| Install optional L4/L5 pulls | ✅ implemented | `daari install --pull-l4 --pull-l5` env passthrough to script |

## Verification results

- `pytest -m "not integration and not benchmark"`: **72 passed, 2 deselected**
- `OLLAMA_HOST=http://127.0.0.1:11434 pytest -v`: **74 passed**
- `pytest -m benchmark`: **1 passed**
- `./scripts/demo.sh`: **pass**
- `./scripts/bench.sh`: **pass**
- Manual curl smoke (fresh daemon + clean cache):
  - L3-first: `L3`
  - L0 repeat: `L0`
  - L1 paraphrase: `L1`
  - L2 transform: `L2`
  - Lt command: `Lt`
  - L4 override: fallback to `L3` with `l4_unavailable_fell_back_to_l3` warning when model not installed
  - No-frontier header: handled (`L3`, local path)
  - Streaming SSE metadata: pass (`daari_meta` present in stream chunk events)
  - Anthropic adapter (`/v1/messages`): pass (manual curl + integration test)
  - MCP stub (`/v1/mcp/query`): covered by integration test (`501 Not Implemented`)
  - L6: implementation validated by tests; live manual call skipped because no frontier API key in environment

## Performance summary

Measured on local machine against a clean daemon instance (`scripts/bench.sh` + targeted probes):

| Tier/path | Observed p50 latency |
|-----------|----------------------|
| L0 exact cache | bench probe returned `L3` (~450.5 ms), indicating no L0 hit in that run |
| L1 semantic cache | bench probe returned `L3` (~833.2 ms), indicating no L1 hit in that run |
| L2 rules | ~60.4 ms |
| Lt command (`git status`) | ~57.9 ms |
| L3 local model | ~812.0 ms |
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
| Medium | Anthropic adapter does not stream yet | Claude-style streaming clients still need fallback/non-stream | Add Anthropic SSE event protocol in C2 |
| Medium | MCP gateway is currently stubbed | MCP-native client requests return `501` | Implement C1 MCP ingress contract and handler |
| Medium | L6 manual smoke requires configured API key | Cannot validate live frontier path in keyless env | Add optional key-aware smoke script path |
| Low | Wizard is still single-choice flow | Slight setup friction for first-time setup | Expand wizard to multi-step/multi-select in follow-up |

