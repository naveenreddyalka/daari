# ADR-0001: Frontier fallback policy

Date: 2026-06-15  
Status: **accepted**

## Context

daari routes requests through local tiers (cache, rules, local models) to minimize frontier API usage. When local tiers produce low-confidence or failed results, we need a policy for what happens next.

## Decision

**Auto-escalate to frontier APIs (OpenAI / Anthropic) as a last resort** when:

- Local model confidence score is below configured threshold, or
- Local execution errors after exhausting appropriate local tiers, or
- Task classification marks the request as requiring frontier-class reasoning *and* local tiers decline

Frontier is **L6** — never the default path. Routing must always attempt cheaper local tiers first.

## Consequences

**Positive**
- Quality preserved for hard tasks without manual intervention
- Still achieves majority frontier avoidance for small/repeated/cacheable work
- Clear escalation story in logs (`tier: L6, reason: low_confidence`)

**Negative**
- Requires API keys configured even for "local-first" setup
- Risk of silent frontier spend if confidence thresholds are too aggressive
- Must implement confidence scoring and spend logging from MVP

## Implementation notes

- Config: `frontier.enabled`, `frontier.providers`, `frontier.confidence_threshold`
- Every L6 call logged with estimated cost and escalation reason
- CLI flag `--no-frontier` for sessions that must stay 100% local
