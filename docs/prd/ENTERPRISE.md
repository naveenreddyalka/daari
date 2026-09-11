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

## Where daari stands (verified in-tree, 2026-09-11)

**The loop is healthy.** The 09-10 refill (#409–#412) and leftover #398 all
merged (PRs #404, #414–#417). `scripts/autodev_backlog.py --pick` was empty
this morning; stall issue #408 was closed by hand after #404 landed. Open
feature PRs: none. [#373](https://github.com/naveenreddyalka/daari/pull/373)
(brew v1.4.0) is still `BEHIND` — HITL, not auto-merge.

**`AUTODEV_GH_TOKEN` remains set.** Labels on this run's issues (#418–#422)
stuck at create time.

**Positioning:** LiteLLM's 09-10
[harness-aware routing](https://docs.litellm.ai/blog/auto-router-harness-aware-classification)
strips Claude Code system text and Codex `<environment_context>` /
`<recommended_plugins>` from the *classifier* only. That is today's headline
and the strongest inward miss: `build_prompt_profile` still sums every
message into `tokens_est`, so a Cursor/Claude Code skill catalog flips
`complexity=complex`. Portkey v2.21 multi-JWKS and Kong context-window
pricing already have daari counterparts (#411 shipped; multi-JWKS filed as
P3). Ollama 0.34 GA and SEP-1933 draft — unchanged from 09-10.

---

## Scored gap table

| # | Gap | Impact | Effort | Who does it best today | Why daari wins local-first | Action |
|---|-----|:--:|:--:|------------------------|----------------------------|--------|
| 1 | **Harness catalogs flip complexity** — `tokens_est` counts system/skill catalogs; `>2000` → `complex` / L4 hop on a one-line ask | 4 | 2 | [LiteLLM harness-aware (09-10)](https://docs.litellm.ai/blog/auto-router-harness-aware-classification) | Strip envelopes locally; no classifier call; #385 still sees full tokens | **Filed [#418](https://github.com/naveenreddyalka/daari/issues/418)** (P2) |
| 2 | **Stall issues stay open after the PR merges** — watcher files `autodev-pr-stall` but never closes; #408 sat open after #404 | 3 | 1 | (loop self-healing) | Same `gh` path the watcher already uses | **Filed [#419](https://github.com/naveenreddyalka/daari/issues/419)** (P2) |
| 3 | **Anthropic `output_format` ignored** — #398 covers OpenAI `response_format.json_schema` only; Claude Code sends `output_format` | 3 | 2 | OpenAI / Anthropic structured outputs | Same Ollama `format` object as #398 | **Filed [#420](https://github.com/naveenreddyalka/daari/issues/420)** (P2) |
| 4 | **`classify_user_turn` default off for agents** — Cursor/Claude Code pay the re-profile tax unless an operator finds the knob | 3 | 2 | LiteLLM `classification_mode: user_turn` | UA already sniffed (`cursor` → client_id) | **Filed [#421](https://github.com/naveenreddyalka/daari/issues/421)** (P2) |
| 5 | **Single JWKS URL** — `sso.jwks_url` cannot trust two IdPs | 2 | 2 | [Portkey v2.21](https://portkey.ai/docs/changelog/enterprise) | Cached JWKS fetch already on-box | **Filed [#422](https://github.com/naveenreddyalka/daari/issues/422)** (P3) |
| 6 | **Batch API** — no `/v1/batches` | 4 | 4 | OpenRouter Batch API | Idle local tiers overnight | Watch |
| 7 | **MCP agent identity** — [SEP-1933](https://github.com/modelcontextprotocol/modelcontextprotocol/pull/1933) still **draft** | 3 | 3 | MCP Tier-1 SDKs | `secret://oauth` + key expiry ready | Watch |
| 8 | **SOC 2 / trust center** | 3 | 5 | LiteLLM | Audit hash chain (#378) is customer-verifiable, not an auditor PDF | Non-goal |
| 9 | **Gemini facade / A2A / admin UI / off-peak / `/v1/images` / WIF** | 2–3 | 2–4 | Kong / LiteLLM / Portkey | No client demand this run | Watch / non-goal |

09-10 rows #409–#412 and #398 shipped and are pruned.

Open backlog after this run:
[#418](https://github.com/naveenreddyalka/daari/issues/418)–[#421](https://github.com/naveenreddyalka/daari/issues/421) (P2),
[#422](https://github.com/naveenreddyalka/daari/issues/422) (P3).

---

## Path to enterprise-grade — next 5 milestones

1. **Harness-aware profiling**
   ([#418](https://github.com/naveenreddyalka/daari/issues/418)): stop
   Cursor/Claude Code catalogs from forcing L4 on a one-line ask — LiteLLM's
   current headline, without a classifier hop.
2. **Close stall issues on merge**
   ([#419](https://github.com/naveenreddyalka/daari/issues/419)): #408 should
   not need a human.
3. **Anthropic structured output**
   ([#420](https://github.com/naveenreddyalka/daari/issues/420)): same
   `json_schema` path as #398 on `/v1/messages`.
4. **Agent-UA user-turn classification**
   ([#421](https://github.com/naveenreddyalka/daari/issues/421)): turn the
   #389 knob on for Cursor / Claude Code / Codex automatically.
5. **HITL:** merge [#373](https://github.com/naveenreddyalka/daari/pull/373)
   (brew v1.4.0, BEHIND). Multi-JWKS (#422) when a fleet has two IdPs.

---

## Changelog

- **2026-09-11** — 09-10 refill + #398 shipped; backlog empty; #408 closed
  by hand. Outward: LiteLLM harness-aware routing (09-10). Inward verified:
  `build_prompt_profile` counts all message chars; stall issues never
  auto-close; Anthropic `output_format` absent; `classify_user_turn` still
  global-off. Filed [#418](https://github.com/naveenreddyalka/daari/issues/418)–[#421](https://github.com/naveenreddyalka/daari/issues/421)
  (P2) and [#422](https://github.com/naveenreddyalka/daari/issues/422) (P3).
- **2026-09-10** — Filed #409–#412; `AUTODEV_GH_TOKEN` set; Ollama 0.34 GA
  verified; Portkey v2.21; LiteLLM identity-aware agents.
- **2026-09-09 evening** — Filed #397–#401.
- **2026-09-09 pm** — Filed #385–#389.
- **2026-09-09** — Park over, v1.4.0 released. Filed #374–#378.
- **2026-09-08** — Nine-PR park; filed #368 / #369.
- **2026-09-07→08-28** (condensed) — Affinity, stall, MCP pages, labeler,
  Apache 2.0, this PRD.
