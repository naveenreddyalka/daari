# Release notes — v1.2.0 (Learning, Trust & Clients)

> Date: 2026-07-23  
> Scope: everything merged since v1.1.2 — 26 commits across four feature programs, all live-E2E validated on the local daemon

## Summary

daari now **learns from your usage** (feedback loop, routing tuner, LoRA
fine-tune pipeline), **measures its own cache trustworthiness** (shadow-sampled
false-hit rate — a metric none of the compared commercial routers ship),
**connects to more clients in one click** (Claude Code with full agent tool
passthrough, JetBrains/Zed/Continue via an Ollama-compatible facade), and
**secures public tunnel exposure** with gateway API-key auth.

## Highlights by program

### Phase D — Local learning (#56–#66)

| Feature | Detail |
|---------|--------|
| Outcome store (D1a) | Implicit capture of category/tier/confidence/escalation per request; explicit accept/reject via `POST /v1/daari/feedback` |
| Evidence-based recommendations (D1b) | `daari learn stats` + `daari learn recommend` emit a ready-to-paste `routing.category_policies` block |
| Routing tuner (D1c) | Per-category confidence thresholds adjusted from outcomes (`learning.auto_tune`) |
| Example capture (D2a) | Opt-in full (prompt, completion) capture; rejects are deleted |
| Dataset export (D2b) | `daari learn export-dataset` → mlx-lm chat-format train/valid JSONL |
| LoRA runner (D2c) | `daari learn finetune` plans + runs `mlx_lm lora --train` with auditable run.json |

### Trust & Efficiency trains (#70, #75, #79)

| Train | Detail |
|-------|--------|
| Cache trust | Embedding-input normalization; per-category answer-diversity monitor; **shadow sampling of L1 hits → measured false-hit rate** that auto-raises the similarity threshold |
| Token savings | Anthropic `cache_control` prompt-cache hint on L6; conversation compaction (old history summarized by L3); sentence-level relevance compression before L6 |
| Latency-aware routing | `daari profile` hardware benchmarks; `routing.latency_budget_ms` + per-category + `X-Daari-Latency-Budget`; warm-model preference via `/api/ps` |
| Learned routing | `daari learn train-router` centroid classifier; overrides heuristics when confident |
| Budget & client UX | Monthly + soft budgets with `frontier_budget_warning`; per-client ledger attribution + `daari report --by-client`; opt-in pre-L6 PII scrub |

### One-click clients (#82, #85, #89)

| Feature | Detail |
|---------|--------|
| Claude Code one-click | `daari setup claude-code` merges the `env` block into `~/.claude/settings.json`; undo restores backup or strips daari keys |
| **Anthropic tool passthrough** | Full agent E2E: `tools`/`tool_use`/`tool_result` flow through the router; streamed `tool_use` blocks with `stop_reason: "tool_use"` |
| Ollama-compatible facade | `/api/tags`, `/api/chat` (NDJSON stream), `/api/version`, `/api/show`, `/api/ps` — JetBrains AI Assistant, Zed, Continue connect by pasting `http://127.0.0.1:11435` |
| Live-session fixes | Ollama 400 bodies preserved in logs; `num_ctx` sized from prompt (4096–32768) so large agent system prompts stop truncating; tool-call args JSON-string→object |

### Security & routing controls (#87, #92)

| Feature | Detail |
|---------|--------|
| Gateway API-key auth | `server.api_key` + middleware (Bearer / `x-api-key`); `daari setup cursor --tunnel` auto-generates and wires the key |
| Per-project profiles | `.daari.yaml` at repo root (`max_tier_for_chat`, `no_frontier`, `latency_budget_ms`, `client_id`) + `X-Daari-Project` header; `daari project init/show` |

### Platform (#47–#50)

Streaming L1 semantic cache + draft injection, request-log rotation, embedding
LRU memoization, and the web-UI usage/savings/traces dashboard.

## Testing

- Suite: **489 pytest** (162 at v1.1.2) + ruff, plus browser-extension and
  web-ui DOM suites — all green in CI (test/lint/sanity/extension required
  checks on `main`).
- Live E2E battery (2026-07-22, running daemon): 11/11 — OpenAI fresh→L3,
  repeat→L0, SSE stream, Anthropic `system` + streamed `tool_use`, facade
  tags/chat, stats/report/traces/diversity endpoints.
- Per-project profile cap live-verified A/B: same long prompt L4 without
  header, L3 with `X-Daari-Project`.

## Upgrade notes

- All new behaviors are default-safe: normalization + shadow sampling are on
  (read-only additions); compaction, compression, learned router, PII scrub,
  example capture, and budgets are **opt-in** via `~/.daari/config.yaml`.
- If you expose daari through a tunnel, re-run `daari setup cursor --tunnel`
  once to generate `server.api_key`, then restart the daemon.
- Claude Code users: `daari setup claude-code` is now fully agent-capable;
  expect reduced quality vs Claude on complex multi-step work (local models),
  not missing functionality.
