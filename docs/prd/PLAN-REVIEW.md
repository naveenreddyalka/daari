# Plan & PRD Review — Issue Tracker

> **Last updated:** 2026-06-15  
> **PRD version:** v0.4  
> **Related:** [PRD](PRD.md) · [Competitive landscape](../discovery/04-competitive-landscape.md)

---

## Summary

| Status | Count |
|--------|-------|
| ✅ Resolved | 18 |
| ⏳ Open | 0 |

All plan review issues addressed in docs. Ready for PRD v0.4 approval gate.

---

## Critical issues

### 1. Positioning says "proxy" — understates product

**Status:** ✅ **Resolved** (PRD v0.3+)

Product principles section; "local execution router" / "local cost optimizer" language throughout.

---

### 2. MVP too large for solo builder

**Status:** ✅ **Resolved** (PRD v0.3+)

Tracer bullet Phase A defined. Explicit defer list. Phase A.1 for setup + L6.

---

### 3. Router quality hand-waved

**Status:** ✅ **Resolved**

→ [`routing-spec.md`](routing-spec.md): classifier inputs, heuristics, confidence scoring, escalation, 20 golden prompts.

---

### 4. Lt tier hardest to build

**Status:** ✅ **Resolved**

- Phase B.0: git, formatter, linter only
- Phase B.1: IntelliJ + destructive confirmation
- PRD user story #14
- routing-spec Lt patterns with `X-Daari-Confirm-Tool`

---

### 5. Agent tool-call compatibility minefield

**Status:** ✅ **Resolved**

→ [ADR-0004](../adr/0004-agent-tool-call-compatibility.md)

---

### 6. Claude Code may not use OpenAI-compat

**Status:** ✅ **Resolved**

Client support matrix in PRD; Claude Code Phase B; Anthropic gateway Phase C2; setup-spec documents limitation.

---

### 7. Success metrics lack baseline

**Status:** ✅ **Resolved** (PRD v0.3+)

$0 tier rate, local AI rate, frontier rate, cost saved vs all-L6 baseline.

---

### 8. Open source strategy underspecified

**Status:** ✅ **Resolved** (PRD v0.3+)

OSS & privacy commitments section + ADR-0006 telemetry off by default.

---

## Medium issues

| # | Issue | Status | Resolution |
|---|-------|--------|------------|
| 9 | Language undecided | ✅ | [ADR-0005](../adr/0005-python-tech-stack.md) — Python 3.12 |
| 10 | PRD-PLAN status stale | ✅ | Updated to Phase 5 / v0.4 |
| 11 | No glossary | ✅ | [`glossary.md`](glossary.md) |
| 12 | Phase C too bundled | ✅ | Split C1 (MCP, profiles) / C2 (Anthropic, IDE) |
| 13 | daari.dev/install fake | ✅ | [`setup-spec.md`](setup-spec.md) — `./install.sh` only for MVP |
| 14 | Eval deferred to v1 | ✅ | 20 golden prompts in routing-spec; Phase A eval |
| 15 | Setup reversibility | ✅ | [`setup-spec.md`](setup-spec.md) — backup + `--undo` |

---

## Low issues

| # | Issue | Status | Resolution |
|---|-------|--------|------------|
| 16 | Approval checklist incomplete | ✅ | All ADRs 0001–0006 + specs in PRD |
| 17 | Discovery frontier TBD | ✅ | Fixed in `02-discovery.md` |
| 18 | No threat model | ✅ | [ADR-0006](../adr/0006-local-daemon-security.md) |

---

## Next steps (post-review)

1. **You approve PRD v0.4** — check approval section in PRD
2. **Implementation plan** — Phase A tracer bullet tasks
3. **Optional:** challenge Python choice (OD-2) before coding starts

---

## What's still hard (known, not blockers)

These are **accepted risks**, not open doc issues:

| Risk | Mitigation in docs |
|------|-------------------|
| Local models weak on agent tool_calls | ADR-0004 → L6 escalation |
| Lt intent matching imperfect | Explicit regex patterns only; confirmation for destructive |
| Solo builder velocity | Tracer bullet MVP scope |
