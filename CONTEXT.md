# daari — Project Context

> Handoff document for any tool or session picking up this project.  
> **Last updated:** June 2026  
> **Project location:** `~/Home/Daari`  
> **GitHub:** https://github.com/naveenreddyalka/daari

---

## Current phase

**Discovery & PRD (draft v0.1)** — vision and PRD drafted; awaiting approval and open decisions.

No application code yet.

## What daari is

A **local inference router**: sits between dev tools (Cursor, CLI) and models. Routes each request through tiered local paths — cache, rules, small/medium/large local models — so frontier APIs (OpenAI, Anthropic) are not used for small, repeated, or cacheable tasks.

See [`docs/prd/PRD.md`](docs/prd/PRD.md) for full draft.

## What we know

| Topic | Decision / draft |
|-------|------------------|
| **Problem** | Frontier APIs overused for trivial/repeated agent tasks |
| **Solution** | Tiered local router (L0 cache → L6 frontier optional) |
| **Primary user** | Naveen (personal dev workflow, macOS) |
| **Integration** | OpenAI-compatible local API + CLI |
| **MVP tiers** | L0 exact cache + L3 Ollama + heuristic router |
| **Name** | daari = path (Telugu) — routing metaphor |

## Open decisions

1. **Frontier policy** — never vs opt-in vs auto-escalate ([PRD OD-1](docs/prd/PRD.md#open-decisions))
2. **Language** — Python (recommended MVP) vs Go vs other ([approach options](docs/discovery/03-approach-options.md))
3. **Audience** — solo vs others at v1

## First actions (every session)

1. Read this file
2. Read [`docs/PRD-PLAN.md`](docs/PRD-PLAN.md) — check phase
3. Read [`docs/prd/PRD.md`](docs/prd/PRD.md) and latest [`docs/discovery/`](docs/discovery/)
4. Do not implement until PRD approved

## Related repos

| Repo | Role |
|------|------|
| [`naveenreddyalka/daari`](https://github.com/naveenreddyalka/daari) | This project |
| [`naveenreddyalka/next`](https://github.com/naveenreddyalka/next) | Job search hub — doc patterns |
| `naveenreddyalka/agent-skills` *(planned)* | Reusable agent skills |
