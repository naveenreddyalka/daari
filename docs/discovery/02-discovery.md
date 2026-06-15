# Discovery — daari

> **Status:** Draft  
> **Phase:** 2

---

## Primary persona

**Naveen — local agent power user**

- Uses Cursor / Claude Code / CLI agents daily
- Cares about cost, speed, and keeping code local
- Comfortable running Ollama, Docker, or native inference servers
- Will tolerate setup complexity if daily savings are real
- Wants transparency: "why did this go local vs. not?"

## Jobs to be done

| Job | Example | Ideal path |
|-----|---------|------------|
| Repeat the same kind of task | Generate commit message from diff | L0/L1 cache or L3 SLM |
| Cheap classification | "Is this a test file?" / intent routing | L2 rules or L3 SLM |
| Small transform | Reformat JSON, extract field, rename suggestion | L3 SLM |
| Medium generation | Docstring, unit test skeleton, refactor hint | L4 local model |
| Hard reasoning | Architecture design, subtle bug across files | L5 local or L6 frontier |
| IDE-native op | Rename, refactor, optimize imports | **Lt tool-native (IntelliJ etc.) — no AI** |
| Deterministic | Format, lint, git status | **Lt CLI tools — no AI** |
| Embarrassingly repeated | Same prompt template in a loop | L0 exact cache |

## Current alternatives

| Alternative | Gap |
|-------------|-----|
| **Send everything to Claude/GPT** | Expensive, slow, leaky for small tasks |
| **Ollama alone** | No routing, caching, or task-aware tier selection |
| **LiteLLM / OpenRouter** | Proxy/routing exists but not opinionated local-first + semantic cache |
| **Cursor model picker** | Manual per-request; no automatic tier routing |
| **Prompt caching (provider-side)** | Still frontier-dependent; not local |
| **DIY scripts** | Fragile; no unified path abstraction |

## Constraints

| Constraint | Notes |
|------------|-------|
| **Local-first** | Core requirement — macOS primary |
| **Hardware** | Bounded by user's machine (Apple Silicon assumed) |
| **Privacy** | Prefer no egress for routable tasks |
| **Integration** | Must work with existing tools (OpenAI-compatible API is strong candidate) |
| **Solo builder** | Scope must stay shippable in phases |
| **Observability** | Need to prove routing works (logs, metrics) |

## Risks

| Risk | Mitigation |
|------|------------|
| Local models too weak for some "small" tasks | Tier escalation + quality scoring; tune routing thresholds |
| Cache returns stale/wrong answer | TTL, invalidation rules, cache bypass flag |
| **Setup friction** | Single install + `daari setup --all` + doctor |
| Routing misclassifies → bad output | Confidence thresholds, fallback tier, human override |
| Scope creep into full agent framework | Stay a router/executor; integrate with existing agents |

## Task taxonomy (for routing)

Initial categories daari should recognize:

1. **cache_hit** — exact or semantic match
2. **rule** — deterministic transform, no LLM
3. **classify** — label, route, score (SLM)
4. **extract** — structured pull from text (SLM)
5. **transform** — reformat, shorten, expand lightly (SLM/small)
6. **generate_small** — short completion (medium local)
7. **generate_large** — long or multi-step (large local / frontier TBD)
8. **unknown** — conservative default path

## Integration surfaces

| Surface | Priority | Notes |
|---------|----------|-------|
| OpenAI-compatible HTTP API | P0 | Universal adapter — Cursor, Claude Code, SDKs |
| Setup / installer | P0 | `install.sh`, `daari setup <tool>`, `daari doctor` |
| CLI (`daari run`, `daari route`) | P0 | Debugging and scripts |
| Tool-native executor (Lt) | P1 | IntelliJ CLI, git, linter, formatter |
| MCP server | P2 | Agent-native integration |
| Anthropic-compat gateway | P3 | Tools requiring Claude wire format |

### Supported clients (target)

| Client | Integration | Setup |
|--------|-------------|-------|
| Cursor | OpenAI-compat base URL | `daari setup cursor` |
| Claude Code | OpenAI-compat / env config | `daari setup claude-code` |
| Any OpenAI SDK | `base_url` override | `daari setup openai-compat` |
| IntelliJ | Lt tool backend (not AI client) | `daari setup intellij` |
| Custom CLI/UI | OpenAI-compat | `daari setup detect` |

## Success metrics

| Metric | Target (MVP) |
|--------|--------------|
| Frontier call reduction | ≥50% MVP, ≥70% v1 |
| Cache hit rate (exact + semantic) | ≥20% of requests after warmup |
| p50 latency (local tiers) | <500ms for L0–L3 |
| Routing accuracy | ≥90% on labeled eval set |
| Uptime (local daemon) | Stable for daily dev use |

## Phased product scope

### MVP
- Local daemon with OpenAI-compatible `/v1/chat/completions`
- L0 exact cache + L3 small model (via Ollama)
- Heuristic router
- **`install.sh` + `daari setup cursor` + `daari doctor`**
- Request logging: tier, latency, cache hit/miss

### v1
- L1 semantic cache + L2 rules
- **Lt tool-native** — git, formatter, linter; IntelliJ CLI
- L4 medium model tier
- **`daari setup --all`** for Cursor, Claude Code, IntelliJ, generic clients

### v2+
- L5 large local model tier
- MCP integration
- Eval harness for routing quality
- Optional frontier fallback (if policy allows)
