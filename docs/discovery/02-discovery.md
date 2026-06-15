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
| Hard reasoning | Architecture design, subtle bug across files | L5 local or L6 frontier *(policy TBD)* |
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
| Setup too heavy | Sensible defaults, one-command local stack |
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

## Integration surfaces (candidates)

| Surface | Priority | Notes |
|---------|----------|-------|
| OpenAI-compatible HTTP API | P0 | Drop-in for many tools |
| CLI (`daari run`, `daari route`) | P0 | Debugging and scripts |
| Cursor / IDE config | P1 | Point base URL at daari |
| MCP server | P2 | Agent-native integration |
| File watcher / hook | P3 | Auto-route repeated pipelines |

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
- Simple classifier (heuristic + optional SLM) to pick tier
- Request logging: tier chosen, latency, cache hit/miss

### v1
- L1 semantic cache (local embeddings)
- L2 rules engine (templates, regex, structured ops)
- L4 medium local model tier
- CLI for stats, cache admin, dry-run routing

### v2+
- L5 large local model tier
- MCP integration
- Eval harness for routing quality
- Optional frontier fallback (if policy allows)
