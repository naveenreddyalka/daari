# Vision — daari

> **Status:** Draft — awaiting approval  
> **Phase:** 1

---

## Elevator pitch

**daari** is a **local execution router** — an end-to-end platform that works with Cursor, Claude Code, any CLI, UI, or IDE. It routes each task to the cheapest capable path: cache, rules, **existing tools** (IntelliJ refactor, git, linter — no AI), local models, and only then frontier APIs.

## Problem

Today, agent workflows (Cursor, CLI tools, custom scripts) send almost every request to frontier models. That creates:

| Pain | Why it matters |
|------|----------------|
| **Cost** | Repeated prompts (lint fixes, formatting, classification, summarizing small snippets) burn tokens on models priced for reasoning |
| **Latency** | Network round-trips for trivial tasks that could resolve in milliseconds locally |
| **Privacy** | Code, files, and context leave the machine even when a local model would suffice |
| **No learning from repetition** | Same task types are re-inferred from scratch every time instead of cached or routed cheaply |
| **All-or-nothing routing** | Tools pick one model for everything; there is no intelligent path selection |

## Insight

Most agent workloads are a **mix of task types**, not one homogenous "be smart" job:

- **Repeated** — same shape of request many times (commit messages, test stubs, rename suggestions)
- **Small** — classification, extraction, reformatting, yes/no decisions
- **Cacheable** — identical or near-identical inputs produce stable outputs
- **Rarely frontier-worthy** — only a subset actually needs top-tier reasoning

A **path** (దారి) through local tiers can handle the bulk. Frontier models become optional — or unnecessary — rather than the default.

## Solution (conceptual)

daari sits between your tools and backends. It classifies each request and picks the cheapest capable path — including **non-AI tool-native execution** when an IDE or CLI can do the job.

```
Tool (Cursor, Claude Code, CLI, UI, IDE)
        │
        ▼
   ┌─────────┐
   │  daari  │  ← route, setup, execute locally
   └─────────┘
        │
   ┌────┴────────────────────────────┐
   │ L0 Cache                        │
   │ L1 Semantic cache               │
   │ L2 Rules / templates            │
   │ Lt Tool-native (IDE, git, lint) │  ← no AI
   │ L3 Small local model (SLM)      │
   │ L4 Medium local model           │
   │ L5 Large local model (optional) │
   │ L6 Frontier API (last resort)   │
   └─────────────────────────────────┘
```

## Who it is for

**Primary:** Naveen — personal developer/agent workflow on local machine (macOS).

**Secondary (later):** Other developers who want the same local-first routing without building it themselves.

Not targeting: teams needing managed cloud inference, non-technical consumers, mobile-first users (v1).

## Non-goals (v1)

- Training or fine-tuning models from scratch
- Building a general chat UI (daari is infrastructure, not a ChatGPT clone)
- Replacing IntelliJ, VS Code, or Cursor — daari works **with** them
- Multi-user SaaS or billing
- Windows/Linux support before macOS works well

## Name

**daari** (Telugu: path, way) — the product routes each request to the right **path**: cache hit, rule, or local model tier. The name matches the core mechanic.

## Success (3-month horizon)

- ≥70% of daari-routed requests never touch a frontier API
- Measurable cost/latency reduction vs. baseline "everything to Claude/GPT"
- Stable local API any compatible client can call (Cursor, Claude Code, CLI)
- **Single-command setup** for detected tools (`daari setup --all`)
- Clear tier routing with observable metrics (cache / tool / model / frontier)

## Open decision

**Frontier fallback policy** — see [PRD § Open Decisions](../prd/PRD.md#open-decisions).
