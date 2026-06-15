# Routing Specification — daari

> **Status:** Draft v1.0 — pre-implementation  
> **Related:** [PRD](PRD.md) · [ADR-0004](../adr/0004-agent-tool-call-compatibility.md) · [PLAN-REVIEW](PLAN-REVIEW.md)  
> **Fixes:** Plan review issue #3

---

## Purpose

Define **how** daari classifies requests, selects tiers, scores confidence, and escalates — so routing is testable before code is written.

---

## Routing pipeline (ordered)

```
1. Normalize request
2. Check headers (X-Daari-Tier-Override, X-Daari-No-Cache)
3. L0 exact cache lookup
4. L1 semantic cache lookup        [Phase B]
5. L2 rules match                  [Phase B]
6. Lt tool-native match            [Phase B — git/lint/format only at first]
7. Classify task → initial model tier (L3 default in MVP)
8. Execute at tier
9. Confidence check on result      [Phase A.1 for L6 escalation]
10. Escalate L3 → L4 → L5 → L6 if below threshold
11. Cache write (if cacheable)
12. Return response + daari_meta
```

**MVP (Phase A):** Steps 1–3, 7 (heuristic only), 8 at L3 only, 11–12. No L1/L2/Lt/L4/L5/L6.

---

## Classifier inputs

The router reads these signals from each request:

| Signal | Source | Used for |
|--------|--------|----------|
| `message_count` | messages array length | Multi-turn → skip L0 for some keys |
| `total_tokens` | Estimated token count | Size buckets (see below) |
| `last_user_content` | Final user message text | Keywords, regex, Lt patterns |
| `has_tool_calls` | Request/response history | Agent round — see ADR-0004 |
| `tools_defined` | `tools` array present | Agent mode — routing restrictions |
| `model_requested` | `model` field | Client hint; daari may override internally |
| `stream` | boolean | Affects execution, not tier selection |
| `temperature` | float | Included in L0 cache key |
| `X-Daari-*` headers | HTTP headers | Override / no-cache |

**Not used in MVP:** embeddings, SLM classifier (Phase B hybrid).

---

## Heuristic classifier (Phase A — MVP)

Simple rule chain evaluated top-to-bottom; **first match wins** for tier *ceiling* (max tier allowed before escalation logic):

| Rule ID | Condition | Max tier | Rationale |
|---------|-----------|----------|-----------|
| R-A1 | `total_tokens` < 50 AND matches classify regex¹ | L3 | Tiny classification |
| R-A2 | `total_tokens` < 200 AND matches transform regex² | L3 | Small reformat/extract |
| R-A3 | `total_tokens` < 500 | L3 | Default small local |
| R-A4 | `total_tokens` ≥ 500 AND < 2000 | L4 | Medium generation [Phase B] |
| R-A5 | `total_tokens` ≥ 2000 | L6 | Large context — skip local in MVP, escalate [Phase A.1] |

¹ Classify regex (examples): `(?i)(is this|classify|which type|yes or no|true or false)`  
² Transform regex (examples): `(?i)(format|reformat|convert to json|extract|parse)`

**MVP simplification:** All requests → L3 unless L0 cache hit. Heuristic rules logged but only affect Phase A.1 escalation.

---

## Hybrid classifier (Phase B — v1)

| Stage | Method | Output |
|-------|--------|--------|
| 1 | Heuristic rules (above) | Candidate tier + task type |
| 2 | Lt pattern registry | Lt if high-confidence tool match |
| 3 | SLM prompt (L3) | `{ task_type, suggested_tier, confidence }` if heuristic ambiguous |

**Ambiguous** = heuristic returns default AND `total_tokens` in 200–800 range AND no Lt match.

---

## Task types

| Type | Description | Typical tier |
|------|-------------|--------------|
| `cache_hit` | Exact or semantic match | L0 / L1 |
| `rule` | Deterministic transform | L2 |
| `tool` | CLI/IDE dispatch | Lt |
| `classify` | Label, route, score | L3 |
| `extract` | Pull structured data | L3 |
| `transform` | Reformat, light edit | L3 |
| `generate_small` | Short completion | L3 / L4 |
| `generate_large` | Long reasoning, multi-file | L5 / L6 |
| `agent_turn` | Has tool_calls in history | L3+ (see ADR-0004) |

---

## Confidence scoring

### Phase A (MVP)

No confidence scoring. L3 result always returned. L6 disabled.

### Phase A.1+

| Tier | Confidence source | Pass threshold | Fail action |
|------|-------------------|----------------|-------------|
| L3 | Heuristic: response length > 10 chars AND no refusal phrases³ | 0.7 (binary mapped) | Escalate to L4 |
| L4 | SLM self-eval prompt: "Rate 1-5 completeness" | ≥ 4/5 | Escalate to L5 |
| L5 | Same self-eval | ≥ 4/5 | Escalate to L6 |
| L6 | N/A — terminal | — | Return or error |

³ Refusal phrases: `(?i)(i cannot|i can't|as an ai|i don't have access)`

**Phase B improvement:** Use logprobs from Ollama when available; fall back to self-eval.

### Escalation policy

```
L3 fail → L4 (if configured) → L5 (if configured) → L6 (if frontier.enabled)
```

If `frontier.enabled: false` and all local tiers fail → return best local attempt + `daari_meta.warning: "below_confidence_threshold"`.

Config keys:
```yaml
confidence:
  l3_min: 0.7
  l4_min: 0.8
  l5_min: 0.8
frontier:
  enabled: true
```

---

## Lt matching (Phase B)

Lt runs **only** when pattern match confidence ≥ 0.95. Patterns are explicit — no free-form NLP in v1.

| Pattern ID | Trigger (regex on last user message) | Tool | Destructive? |
|------------|--------------------------------------|------|--------------|
| LT-01 | `(?i)run (eslint|lint)` | eslint | No |
| LT-02 | `(?i)format (this |the )?(file|code)` | prettier | No |
| LT-03 | `(?i)git status` | git status | No |
| LT-04 | `(?i)git diff` | git diff | No |
| LT-05 | `(?i)rename (symbol|method|class)` | intellij refactor | **Yes** |
| LT-06 | `(?i)optimize imports` | intellij | No |

**Destructive ops (LT-05+):** Require `X-Daari-Confirm-Tool: true` header or config `tools.auto_confirm: false` (default) → return confirmation prompt instead of executing.

---

## L0 cache key

```
SHA256(
  normalize(messages) +
  model +
  temperature +
  tools_schema_hash +    # see ADR-0004
  tier_override_or_none
)
```

Skip L0 if `X-Daari-No-Cache: true` or request contains `tool_calls` in messages (agent mid-turn).

---

## Golden prompt eval set

File: `evals/routing/prompts.jsonl` (to be created at implementation)

| ID | Prompt (summary) | Expected tier (MVP) | Expected tier (v1) |
|----|------------------|---------------------|---------------------|
| GP-01 | Exact repeat of prior request | L0 | L0 |
| GP-02 | "Is this a test file?" + 20 lines Java | L3 | L3 |
| GP-03 | "Format as JSON: {foo: 1}" | L3 | L2 or L3 |
| GP-04 | "Write commit message for: " + small diff | L3 | L3 |
| GP-05 | Same commit message request (repeat) | L0 | L0 |
| GP-06 | "Run eslint on src/" | L3 | **Lt** |
| GP-07 | "git status" | L3 | **Lt** |
| GP-08 | "Explain microservices vs monolith" (500+ words) | L3 | L6 |
| GP-09 | "Add docstring to this 10-line function" | L3 | L3 |
| GP-10 | "Refactor this 500-line class for SOLID" | L3 | L5/L6 |
| GP-11 | "What does this regex match?" (short) | L3 | L3 |
| GP-12 | Paraphrase of GP-04 (same intent) | L3 | L1 |
| GP-13 | "Rename method foo to bar in UserService" | L3 | **Lt** (confirm) |
| GP-14 | "Convert this YAML to JSON" (small) | L3 | L2/L3 |
| GP-15 | "Summarize this 3-line error log" | L3 | L3 |
| GP-16 | "Generate unit tests for Calculator" | L3 | L4 |
| GP-17 | Empty/minimal prompt "hi" | L3 | L3 |
| GP-18 | Prompt with `tools` defined (agent) | L3 | L3 (passthrough rules) |
| GP-19 | "Optimize imports in User.java" | L3 | **Lt** |
| GP-20 | Multi-turn: 5 messages debugging session | L3 | L3/L4 |

**MVP pass criteria:** GP-01, GP-05 hit L0; GP-02–GP-04, GP-09, GP-11, GP-15, GP-17 route to L3; no silent failures.

**v1 pass criteria:** ≥90% match expected tier on GP-01–GP-20.

---

## daari_meta response shape

```json
{
  "daari_meta": {
    "tier": "L3",
    "task_type": "generate_small",
    "cache_hit": false,
    "executor": "ollama",
    "model": "llama3.2:3b",
    "latency_ms": 842,
    "confidence": 0.85,
    "escalated_from": null,
    "rule_id": "R-A3"
  }
}
```

---

## Open items (tracked elsewhere)

| Item | ADR / doc |
|------|-----------|
| Tool-call cache/routing | ADR-0004 |
| Lt destructive confirmation | ADR-0003, PRD user story #53 |
| Semantic cache thresholds | OD-3 |
