# daari — Enterprise gap scan (living PRD)

> Maintained by the daily **prd-cycle** automation ([docs/automations/prd-cycle.md](../automations/prd-cycle.md)).
> Mandate: fastest credible path to a production-grade router enterprises run
> instead of LiteLLM, Portkey, Kong AI Gateway, or a cloud gateway — and keep
> the `auto-dev` backlog fed with the next most valuable work.
> Scoring: impact 1–5 (adoption/retention weight), effort 1–5 (subsystems touched,
> invasiveness). Priority label = impact − effort (≥3 → P1, 1–2 → P2, ≤0 → P3).
> Keep under ~300 lines; prune rows that ship or go stale.
> Phase-E org cache/learning spec: [phase-e-enterprise.md](phase-e-enterprise.md).

---

## Where daari stands (verified in-tree, 2026-09-10)

**The 09-09 evening refill shipped overnight.** #397 / #399 / #400 / #401 are
on `main` (PRs #403 / #405 / #406 / #407). The one leftover is
[#398](https://github.com/naveenreddyalka/daari/issues/398) (`json_schema`):
[PR #404](https://github.com/naveenreddyalka/daari/pull/404) has all five
checks green but sits `DIRTY` — and its stall issue
[#408](https://github.com/naveenreddyalka/daari/issues/408) was created
**without labels**, so the backlog picker cannot see it (gap #1 below).

**`AUTODEV_GH_TOKEN` is finally set** (#408 is authored by the PAT identity,
not github-actions[bot]) — the standing HITL ask from four runs is done. The
side effect is the labeling regression above.

**Positioning:** LiteLLM's 09-08 posts sell *identity-aware shared agents*
(per-end-user access + spend on one shared key) and an updated SOC 2 Type 2
report. Portkey woke up after five quiet months: **v2.21.0** (multi-JWKS JWT
auth with user attribution, ElevenLabs). Kong quiet at 2.0.3 but keeps
compounding cost-accounting fidelity (context-window pricing factors,
cache-TTL write pricing). **Ollama v0.34.0 GA'd** — ChatGPT Desktop runs
local models officially; daari's facade surface (#343/#348) verified against
the 0.34 diff, no parity change needed. SEP-1933 still draft (upd 09-07).

---

## Scored gap table

| # | Gap | Impact | Effort | Who does it best today | Why daari wins local-first | Action |
|---|-----|:--:|:--:|------------------------|----------------------------|--------|
| 1 | **Stall issues created unlabeled** — `_cli_create_issue` passes `--label` but PAT-created #408 has none; backlog picker is label-driven, so conflict parks are invisible to the loop | 4 | 1 | (loop self-healing, daari-specific) | Watcher + labeler (#336) already exist; one body line fixes it | **Filed [#409](https://github.com/naveenreddyalka/daari/issues/409)** (P1) |
| 2 | **No end-user attribution on shared keys** — `body.user` parsed but only feeds session affinity; ledger dims are day/client_id/tier/model; no per-user report or cap | 4 | 3 | [LiteLLM identity-aware agents (09-08)](https://docs.litellm.ai/blog) | Identities never leave premises; keys/teams/budgets already shipped, this is the last identity dimension | **Filed [#410](https://github.com/naveenreddyalka/daari/issues/410)** (P2) |
| 3 | **Context-threshold pricing not applied** — settings.py admits gpt-6-astra >272K (2×/1.5×) bills flat; budgets underbill the most expensive requests | 3 | 2 | [Kong `context_window_factor` (2.0.2)](https://developer.konghq.com/ai-gateway/changelog/) | Admission-time 402/downshift *before* the 2× spend, not a report after | **Filed [#411](https://github.com/naveenreddyalka/daari/issues/411)** (P2) |
| 4 | **Client-facing error details skip redaction** — `detail=f"Routing failed: {exc}"` raw; `redact_secrets()` only guards the request log | 3 | 1 | [LiteLLM v1.102-dev fix](https://github.com/BerriAI/litellm/pull/39964) | Process-wide secret registry makes leak-proofing structural | **Filed [#412](https://github.com/naveenreddyalka/daari/issues/412)** (P2) |
| 5 | **`json_schema` dropped** | 3 | 2 | OpenAI structured outputs | Ollama takes `format` schemas natively | **In flight [#398](https://github.com/naveenreddyalka/daari/issues/398)** / [PR #404](https://github.com/naveenreddyalka/daari/pull/404) — unparked by #409 |
| 6 | **Multi-JWKS SSO** — `resolve_jwks_url` takes one URL; Portkey v2.21 merges keys from several IdPs | 2 | 2 | [Portkey v2.21](https://portkey.ai/docs/changelog/enterprise) | Straightforward cache extension | Watch — file when a fleet has two IdPs |
| 7 | **Batch API** — no `/v1/batches` | 4 | 4 | OpenRouter Batch API | Idle local tiers overnight; MCP Tasks (#315) template | Watch |
| 8 | **MCP agent identity** — [SEP-1933](https://github.com/modelcontextprotocol/modelcontextprotocol/pull/1933) still **draft** (upd 09-07) | 3 | 3 | MCP Tier-1 SDKs | `secret://oauth` + key expiry ready | Watch |
| 9 | **SOC 2 / trust center** — LiteLLM ships an updated Type 2 report | 3 | 5 | LiteLLM | Not agent work; positioning: daari's audit hash chain (#378) is verifiable by the customer, not an auditor PDF | Non-goal for the loop; note for humans |
| 10 | **Gemini facade / A2A / admin UI / off-peak / `/v1/images` / WIF upstream auth** | 2–3 | 2–4 | Kong / LiteLLM / Portkey v2.20 | No client demand this run | Watch / non-goal |

Resolved watches: **Ollama 0.34 GA** — `api/types.go` diff only adds cloud
model-recommendation `thinking` metadata; facade (#343/#348) untouched.
Evening rows #397/#399–#401 shipped and are pruned.

Open backlog after this run:
[#398](https://github.com/naveenreddyalka/daari/issues/398) (PR parked, see #409),
[#409](https://github.com/naveenreddyalka/daari/issues/409)–[#412](https://github.com/naveenreddyalka/daari/issues/412).

---

## Path to enterprise-grade — next 5 milestones

1. **Re-arm the loop's self-healing**
   ([#409](https://github.com/naveenreddyalka/daari/issues/409)): stall issues
   must always carry labels; includes unparking
   [PR #404](https://github.com/naveenreddyalka/daari/pull/404) so #398 lands.
2. **Identity-aware shared agents**
   ([#410](https://github.com/naveenreddyalka/daari/issues/410)): per-end-user
   spend attribution and caps on shared virtual keys — LiteLLM's current
   headline, done without identities leaving the building.
3. **Honest long-context billing**
   ([#411](https://github.com/naveenreddyalka/daari/issues/411)): threshold
   pricing so budgets deny *before* the 2× request, not after.
4. **Leak-proof error surfaces**
   ([#412](https://github.com/naveenreddyalka/daari/issues/412)): every
   client-visible detail through the secret registry.
5. **HITL:** merge [#373](https://github.com/naveenreddyalka/daari/pull/373)
   (brew v1.4.0, BEHIND). `AUTODEV_GH_TOKEN` ask is **done** — thank you.

---

## Changelog

- **2026-09-10** — Evening refill shipped overnight (#397/#399/#400/#401);
  backlog empty again. `AUTODEV_GH_TOKEN` set, with a new side effect:
  PAT-created stall issue #408 lost its labels, orphaning conflict-parked
  PR #404. Outward: Ollama 0.34 GA (facade verified, no change); Portkey
  v2.21 after five quiet months (multi-JWKS + user attribution); LiteLLM
  identity-aware shared agents + SOC 2; Kong quiet. Inward verified: no
  end-user ledger dimension; threshold pricing knowingly unapplied
  (settings.py comment); error details bypass `redact_secrets()`. Filed
  [#409](https://github.com/naveenreddyalka/daari/issues/409) (P1) and
  [#410](https://github.com/naveenreddyalka/daari/issues/410)–[#412](https://github.com/naveenreddyalka/daari/issues/412)
  (P2).
- **2026-09-09 evening** — Filed #397–#401 (all P2).
- **2026-09-09 pm** — Filed #385–#389.
- **2026-09-09** — Park over, v1.4.0 released. Filed #374–#378.
- **2026-09-08** — Nine-PR park; filed #368 / #369.
- **2026-09-07→08-28** (condensed) — Affinity, stall, MCP pages, labeler,
  Apache 2.0, this PRD.
