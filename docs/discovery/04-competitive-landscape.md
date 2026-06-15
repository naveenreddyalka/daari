# Competitive Landscape — daari

> **Status:** Draft  
> **Last updated:** 2026-06-15  
> **Related:** [PRD](../prd/PRD.md) · [Plan review](../prd/PLAN-REVIEW.md)

---

## How daari positions itself

daari is **not** an LLM proxy in the LiteLLM sense. It is an **open-source, local-first execution platform** whose primary goal is:

> **Run as much work as possible cheaply on your machine — without AI when you don't need it, with small local models when you do, and cloud only as last resort.**

| Dimension | daari focus |
|-----------|-------------|
| **Open source** | Core router, cache, setup, and tool executors are OSS — you own the stack |
| **Local-first** | Default path is on-device: cache → rules → IDE/CLI tools → local models |
| **Cost** | Minimize spend by tiering; frontier is exception, not default |
| **Not just proxy** | Routes to **non-AI backends** (IntelliJ, git, linter) — competitors mostly don't |
| **Privacy** | Code stays local for everything routable without L6 |
| **Setup** | One-command install + per-tool recipes — consumer-grade for a dev tool |

---

## Category map

```
                    Cloud-first                          Local-first
                        │                                    │
    ┌───────────────────┼───────────────────┐                │
    │                   │                   │                │
 OpenRouter          Portkey              LiteLLM         Ollama
 (multi-provider     (gateway +           (100+ providers  (run models
  routing)            cache + OSS)         + proxy)         locally)
    │                   │                   │                │
    │                   │              Bifrost / GPTCache     │
    │                   │              (cache layers)        │
    │                   │                   │                │
    └───────────────────┴───────────────────┴────────────────┤
                                                              │
                                                         ★ daari ★
                                              local execution router
                                         (cache + tools + local AI + setup)
```

---

## Competitor comparison

### Tier 1 — Closest overlap (LLM gateway / router / cache)

| Product | What it is | Open source? | Local-first? | Semantic cache | Model tier routing | Tool-native (no AI) | Per-tool setup | daari advantage |
|---------|------------|--------------|--------------|----------------|-------------------|---------------------|----------------|-----------------|
| **[LiteLLM](https://github.com/BerriAI/litellm)** | AI gateway — 100+ providers, OpenAI-compat proxy | ✅ Yes (MIT) | ❌ Cloud-oriented; local via Ollama as one backend | ✅ Redis/Qdrant (needs external deps) | ⚠️ Fallback/retry between deployments, not task-aware SLM→large | ❌ | ❌ Manual config | daari: local default, Lt tier, OSS setup recipes, cost-as-goal not provider-breadth |
| **[Bifrost](https://github.com/maximhq/bifrost)** | High-perf Go AI gateway | ✅ Yes | ⚠️ Hybrid | ✅ Built-in semantic + exact | ⚠️ Provider routing | ❌ | ❌ | daari: tool-native execution, dev-tool setup, not enterprise gateway |
| **[GPTCache](https://github.com/zilliztech/GPTCache)** | Semantic cache library | ✅ Yes | ⚠️ Library only | ✅ Core feature | ❌ | ❌ | ❌ | daari: full platform (cache is one tier), not a library you embed |
| **[LocalAI](https://github.com/mudler/LocalAI)** | Local model server, OpenAI-compat | ✅ Yes | ✅ Yes | ⚠️ Limited | ❌ Single-model serve | ❌ | ❌ | daari: routes *between* tiers/backends; LocalAI is a backend, not a router |
| **[Ollama](https://ollama.com)** | Local model runner | ✅ Yes (client) | ✅ Yes | ❌ | ❌ | ❌ | ⚠️ Easy install, no routing | daari **uses** Ollama as L3–L5 executor; adds routing, cache, tools, setup |

### Tier 2 — Cloud gateways (different primary market)

| Product | What it is | Why not a direct competitor |
|---------|------------|----------------------------|
| **[OpenRouter](https://openrouter.ai)** | Multi-model cloud API aggregator | Cloud-first; optimizes model *choice*, not local execution or zero-cost tiers |
| **[Portkey](https://portkey.ai)** | AI gateway (OSS gateway exists) | Enterprise observability, cloud routing; local-first is secondary |
| **Cloudflare AI Gateway** | Edge proxy + cache | Cloud infra; exact-match cache only; not local AI |
| **Kong AI Gateway** | Enterprise API gateway | Org-scale, not personal local dev stack |

### Tier 3 — IDE / agent tools (partial overlap)

| Product | What it is | Overlap | daari relationship |
|---------|------------|---------|-------------------|
| **Cursor** | AI IDE | Uses frontier models for agent work | **Client** — daari sits in front via custom base URL |
| **Claude Code** | CLI agent | Same | **Client** |
| **Continue.dev** | OSS IDE extension | Local model config in-editor | Could use daari as backend; Continue is UI, daari is routing layer |
| **Cline / Aider** | OSS coding agents | Call APIs directly | **Clients** — benefit from daari routing |
| **IntelliJ AI** | IDE + cloud AI | Refactoring without LLM | **Lt backend** — daari invokes native IDE, not its AI |

### Tier 4 — Nothing quite like daari today

No mainstream OSS product combines **all** of:

1. OpenAI-compat gateway for any client  
2. Exact + semantic **local** cache  
3. **Tool-native tier** (IDE/CLI without AI)  
4. Task-aware **local model tiering** (SLM → medium → large)  
5. Frontier as **last-resort** escalation  
6. **One-command setup** per dev tool  

Closest stack today is **DIY**: LiteLLM + Ollama + shell scripts + manual Cursor config. daari productizes that glue with local-first intent.

---

## daari vs "just use LiteLLM + Ollama"

| Need | DIY (LiteLLM + Ollama) | daari |
|------|------------------------|-------|
| Run local models | ✅ Configure Ollama backend | ✅ Ollama as L3–L5 |
| Avoid cloud cost | ⚠️ You must configure; default is multi-cloud | ✅ Local path is default |
| Cache repeated prompts | ⚠️ Setup Redis/Qdrant + embeddings | ✅ L0/L1 built-in, local store |
| Skip AI for lint/format/refactor | ❌ Still goes to some model | ✅ Lt tool-native tier |
| Setup Cursor / Claude Code | ❌ Manual docs | ✅ `daari setup <tool>` |
| Task-aware routing (small vs large) | ❌ Model alias only | ✅ Router + confidence escalation |
| Open source | ✅ LiteLLM is OSS | ✅ daari is OSS |
| Prove savings | ⚠️ LiteLLM spend tracking (cloud-oriented) | ✅ Per-tier metrics: cache/tool/local/frontier |

**Summary:** LiteLLM is a **provider gateway**. daari is a **local cost optimizer** that happens to speak OpenAI-compat on the front.

---

## Differentiation summary (elevator version)

| | Cloud gateways | Local runners | **daari** |
|---|----------------|---------------|-----------|
| **Primary goal** | Access many models | Run one model locally | **Minimize cost — local path for max tasks** |
| **Open source** | Mixed | Mostly yes | **Yes — full stack OSS** |
| **Non-AI execution** | No | No | **Yes — IDE/CLI tools** |
| **Caching** | Add-on / cloud | Rare | **First-class L0/L1** |
| **Setup for dev tools** | Manual | N/A | **One-command recipes** |
| **Best for** | Teams, multi-cloud | Single local model | **Solo dev, local-first, cost-conscious agents** |

---

## Risks from competitive landscape

| Risk | Mitigation |
|------|------------|
| LiteLLM adds local-first routing | Ship Lt tier + setup UX early; daari's moat is tool-native + installer |
| Ollama adds routing/caching | daari orchestrates Ollama; can adopt new Ollama features as backends |
| Cursor builds local routing in-product | daari stays tool-agnostic (Claude Code, CLI, IntelliJ too) |
| "Good enough" DIY stack | `daari setup --all` must be dramatically easier than docs + yaml |
| Scope vs mature gateways | Stay narrow: **local cost optimization**, not 100-provider enterprise gateway |

---

## Strategic choices (recommended)

1. **License:** Apache 2.0 (already in repo) — align with Ollama/LiteLLM ecosystem  
2. **Messaging:** "Open-source local execution router" — not "another LLM proxy"  
3. **Integrate, don't compete:** Ollama as default backend; optional LiteLLM compat later if needed  
4. **MVP proof metric:** % requests handled at L0/L1/L2/Lt with $0 marginal cost  
5. **Publish benchmark:** daari vs direct Claude vs LiteLLM+Ollama on a standard dev prompt set

---

## References

- LiteLLM: https://github.com/BerriAI/litellm  
- Ollama: https://ollama.com  
- LocalAI: https://github.com/mudler/LocalAI  
- GPTCache: https://github.com/zilliztech/GPTCache  
- Bifrost: https://github.com/maximhq/bifrost  
- Continue: https://github.com/continuedev/continue  
