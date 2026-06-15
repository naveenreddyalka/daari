# Plan & PRD Review — Issues and Recommendations

> **Reviewer:** AI-assisted review (2026-06-15)  
> **Scope:** PRD v0.2, PRD-PLAN, discovery docs, ADRs  
> **Related:** [Competitive landscape](../discovery/04-competitive-landscape.md)

---

## Executive summary

The plan is **directionally strong** and differentiated on **Lt (tool-native)** + **setup UX** + **local cost goal**. Main risks are **scope creep**, **under-specified routing quality**, and **positioning drift toward "proxy"** when the real product is **open-source local cost optimization**.

---

## Critical issues (fix before implementation)

### 1. Positioning says "proxy" in places — understates the product

**Issue:** OpenAI-compat gateway is correct technically, but "proxy" implies pass-through to cloud providers. User intent is **open source, local AI, run cheaply**.

**Fix:** Reframe everywhere as **local execution router** / **local cost optimizer**. Gateway is an adapter, not the product identity.

**Status:** Addressed in PRD v0.3 positioning section + competitive doc.

---

### 2. MVP is still too large for solo builder

**Issue:** Phase A lists daemon + cache + Ollama + router + CLI + setup + doctor + Cursor recipe. Phase B adds semantic cache, Lt, L4, L6 escalation, multi-tool setup, eval harness — in one wave.

**Risk:** Six months of work disguised as "MVP."

**Recommendation — tracer bullet MVP:**

| Ship first (2–3 weeks) | Defer |
|------------------------|-------|
| Daemon + OpenAI-compat | Semantic cache (L1) |
| L0 exact cache | Lt / IntelliJ |
| L3 single Ollama model | L4/L5 tiers |
| Heuristic router (length/keywords) | Confidence scoring |
| `daari serve` + `daari stats` | `daari setup` automation |
| Manual Cursor config doc | `daari setup --all` |

**Proof point:** One tool (Cursor), one model, cache hits measurable, frontier call count drops.

---

### 3. Router quality is hand-waved

**Issue:** "Hybrid classifier" and "confidence thresholds" are core to the value prop but undefined. Bad routing → bad outputs → users disable daari.

**Missing specs:**
- What inputs does the classifier use? (token count, tool_calls presence, file extensions in prompt, regex?)
- Confidence score source? (logprobs, self-eval prompt, heuristic?)
- Escalation thresholds per task type?
- What happens when L3 and L4 both fail confidence — always L6?

**Recommendation:** Add `docs/prd/routing-spec.md` before Phase 6 implementation plan, with 20–30 labeled golden prompts.

---

### 4. Lt (tool-native) is the differentiator but hardest to build

**Issue:** Mapping natural-language agent requests → IntelliJ refactor CLI is an unsolved NLP + IDE integration problem. PRD treats it like git subprocess.

**Risks:**
- IntelliJ headless CLI is limited and project-specific
- Cursor sends chat completions, not structured "rename symbol X" intents
- False-positive tool dispatch could corrupt codebase

**Recommendation:**
- MVP Lt: **git, formatter, linter only** (deterministic, CLI-known)
- v1: IntelliJ with **explicit intent patterns** + user confirmation for destructive ops
- Add user story: "confirm before Lt executes destructive IDE action"

---

### 5. OpenAI-compat + agent tool-calls is a compatibility minefield

**Issue:** Cursor and Claude Code send `tools` / `tool_calls` in payloads. Cache keys, routing, and Lt dispatch all break if not specified.

**Missing:**
- Cache key includes tools schema or not?
- Passthrough behavior for tool-call rounds
- Streaming + tool_calls interleave rules

**Recommendation:** Add ADR-0004: Agent tool-call compatibility policy.

---

### 6. Claude Code may not use OpenAI-compat

**Issue:** PRD assumes `daari setup claude-code` via base URL. Claude Code primarily uses Anthropic API shape.

**Impact:** "Universal minimal change" claim is partially false for MVP.

**Recommendation:**
- MVP: Cursor + generic OpenAI SDK only
- Phase B: Anthropic-compat gateway OR document Claude Code limitation honestly in PRD

---

### 7. Success metrics lack cost baseline

**Issue:** "≥70% frontier avoidance" — avoidance of what baseline? Direct Cursor usage? All requests including cache?

**Recommendation:** Define metrics:

| Metric | Definition |
|--------|------------|
| `$0 tier rate` | % requests handled at L0/L1/L2/Lt |
| `local AI rate` | % at L3–L5 |
| `frontier rate` | % at L6 |
| `cost saved` | Estimated $ vs all-L6 baseline on eval set |
| `p50 latency` | Per tier |

---

### 8. Open source strategy underspecified

**Issue:** User cares about OSS + local. PRD mentions Apache license but not:

- Dependencies policy (all OSS?)
- Model weights (user brings via Ollama — fine)
- Optional telemetry default-off?

**Recommendation:** Add to PRD: **100% OSS core**, no phone-home, frontier keys user-owned, telemetry opt-in only.

---

## Medium issues (address during PRD approval)

| # | Issue | Recommendation |
|---|-------|----------------|
| 9 | Language still undecided (OD-2) | Pick Python for MVP; ADR-0004 tech stack |
| 10 | PRD-PLAN status stale (says v0.1) | Update to v0.2/v0.3 |
| 11 | No glossary | Add `docs/prd/glossary.md` (L0–L6, Lt, tier, path) |
| 12 | Phase C bundles MCP + Anthropic + profiles | Split Phase C into C1/C2 |
| 13 | `curl daari.dev/install` — domain doesn't exist | Mark as future; `install.sh` in repo for now |
| 14 | Eval harness in v1 but routing is MVP-critical | Move 10-prompt eval to MVP |
| 15 | Reversibility of `daari setup` undefined | Setup writes backup before patch |

---

## Low issues / nits

- Approval checklist references ADR-0001 only — should include 0002, 0003
- Discovery doc still says frontier "policy TBD" in one table row — fixed in PRD, not discovery
- No threat model for local daemon (localhost binding, API key optional?)

---

## What's working well

| Strength | Why it matters |
|----------|----------------|
| **Lt tool-native tier** | No competitor does this; aligns with "not everything needs AI" |
| **Tiered model (L0–L6)** | Clear mental model; maps to cost |
| **Setup module vision** | Real pain point vs DIY LiteLLM stacks |
| **ADR discipline** | Decisions tracked early |
| **Phased delivery section** | Exists — just needs narrower MVP |
| **Auto-escalate frontier (ADR-0001)** | Pragmatic quality fallback |

---

## Recommended PRD changes (v0.3)

1. Add **Product principles** section: OSS, local-first, cost-minimize, not-a-proxy
2. Add **Competitive landscape** link and 3-sentence differentiation
3. Narrow **Phase A MVP** to tracer bullet (see issue #2)
4. Add **Open source & privacy** commitments
5. Honest **client support matrix** (Cursor MVP; Claude Code Phase B)
6. Add **Routing spec** as pre-implementation deliverable
7. Fix metrics definitions

---

## Suggested next steps

1. You approve repositioning (local cost optimizer, not proxy)
2. Narrow MVP scope in PRD
3. Pick Python vs Go (OD-2)
4. PRD v0.3 approval
5. Write `routing-spec.md` + implementation plan
