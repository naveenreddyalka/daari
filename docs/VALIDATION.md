# daari — Validation Summary

> Date: 2026-06-20  
> Scope: Phase B core features requested in implementation mandate

## Feature checklist vs PRD

| Feature set | Status | Notes |
|-------------|--------|-------|
| L2 rules engine | ✅ implemented | Deterministic JSON/YAML transforms before model tiers |
| L2-dev developer command rules | ✅ implemented | Regex detection for git/test/lint/readonly command-context prompts |
| CCS command context store | ✅ implemented | Disk-backed command output cache with TTL reads before re-run |
| Lt B.0 dispatch | ✅ implemented | `git status`, `git diff`, `pytest`, `eslint` execution via subprocess |
| PolicyEngine B.0 | ✅ implemented | allow/block/unknown(deny or ask) decisions before Lt |
| L4 medium local tier | ✅ implemented | L3→L4→L6 escalation path (L4 fallback to L3 when unavailable) |
| Model routing preferences | ✅ implemented | `routing.prefer` + `models.weights` config shape and tier picker usage |
| `--no-frontier` / no-frontier header | ✅ implemented | CLI flag + `X-Daari-No-Frontier` request override |
| Streaming SSE | ✅ implemented (basic) | OpenAI-style chunk stream passthrough for `stream=true` |
| Wizard polish | ✅ implemented (partial) | frontier key hint + L3/L4 preference/model setup flow |
| `daari install` Typer parity | ✅ implemented (minimal) | CLI wrapper to run `scripts/install.sh` with doctor option |
| Eval GP-11–GP-20 | ✅ implemented | prompts expanded and regression assertions updated |
| ProviderRegistry router wiring | ✅ implemented (minimum) | model executors registered and resolved through registry |

## Verification results

- `pytest -m "not integration and not benchmark"`: **64 passed**
- `OLLAMA_HOST=http://127.0.0.1:11434 pytest`: **66 passed**
- `pytest -m benchmark`: **1 passed**
- `./scripts/demo.sh`: **pass**
- Manual curl smoke (fresh daemon + clean cache):
  - L3-first: `L3`
  - L0 repeat: `L0`
  - L1 paraphrase: `L1`
  - L2 transform: `L2`
  - Lt command: `Lt`
  - L4 override: fallback to `L3` with `l4_unavailable_fell_back_to_l3` warning when model not installed
  - No-frontier header: remains local (`L3`)
  - L6: implementation validated by tests; live manual call skipped because no frontier API key in environment

## Performance summary

Measured on local machine against a clean daemon instance (`scripts/bench.sh` + targeted probes):

| Tier/path | Observed p50 latency |
|-----------|----------------------|
| L0 exact cache | ~17.6 ms |
| L1 semantic cache | ~69.5 ms |
| L2 rules | ~19.5 ms |
| Lt command (`git status`) | ~60.9 ms |
| L3 local model | ~767.5 ms |
| L4 override (fallback path) | ~2169.2 ms (fell back to L3 when L4 missing) |

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
| High | `daari setup openai-compat` not implemented | Generic SDK setup still manual | Add recipe + docs |
| Medium | L4 model not auto-installed; can fallback to L3 | Reduced quality path unless user pulls L4 model | Extend install/model setup to pull configured L4 |
| Medium | SSE implementation is basic passthrough only | No tier-aware streaming metadata yet | Add richer streaming meta/events in Phase C |
| Medium | L6 manual smoke requires configured API key | Cannot validate live frontier path in keyless env | Add optional key-aware smoke script path |
| Low | Wizard still single-choice flow | Slight setup friction | Expand wizard to multi-step/multi-select in follow-up |

