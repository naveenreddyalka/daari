# Discovery Kickoff — daari

> **Started:** 2026-06-15  
> **Phase:** 2–4 — Discovery + PRD draft (in progress)

---

## Session log

| Date | Notes |
|------|-------|
| 2026-06-15 | Repo scaffolded. PRD plan written. Ready for vision discovery. |
| 2026-06-15 | Q1 answered: local inference router — avoid frontier APIs for small/repeated/cacheable tasks. Vision + PRD draft written. |

---

## Open questions (answer in order)

### Q1 — The core idea ✅

**Answer:** Build a **local inference router** (daari). Route small, repeated, and cacheable tasks through local tiers (cache → rules → local models). Do **not** call OpenAI/Anthropic frontier models for work that does not need them. Multiple local levels as needed.

→ Captured in [`01-vision.md`](01-vision.md) and [`../prd/PRD.md`](../prd/PRD.md)

---

### Q2 — Audience *(current)*

Who is the primary user? Just you, or others too?

*Draft assumption: you first, other devs later — confirm or correct.*

### Q3 — Platform *(after Q2)*

Where should it run? Browser, phone, terminal, desktop, API?

### Q4 — Relationship to "path" *(optional)*

Does the Telugu meaning of daari (path, way, road) matter to the product story?

---

## Raw notes

- Main thing: local execution, no frontier for smaller/repeated/cacheable work
- Tiered local stack — "any levels of local stuff" TBD in detail
- PRD v0.2: universal clients, Lt tool-native tier, setup module, OpenAI-compat rationale
