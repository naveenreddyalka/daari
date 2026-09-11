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

## Where daari stands (verified in-tree, 2026-09-11 late)

**The loop drained the morning refill in under two hours.** #418–#422 are on
`main` (PRs #425–#429). Homebrew formula [#373](https://github.com/naveenreddyalka/daari/pull/373)
merged. Backlog was empty again; this run restocks it.

**Positioning:** LiteLLM's stable headline is still harness-aware routing
(shipped here as #418) plus v1.100 access-group budgets. v1.102-dev adds
percentile-TTFT routing — watch until it leaves `-dev`. Kong is compounding
**service-tier** and **cache-TTL write** pricing. Portkey public changelog
still quiet post-PANW. Ollama **0.34 GA** facade already verified; 0.33.3
cached-token reporting is #399.

---

## Scored gap table

| # | Gap | Impact | Effort | Who does it best today | Why daari wins local-first | Action |
|---|-----|:--:|:--:|------------------------|----------------------------|--------|
| 1 | **`service_tier` dropped** — zero in-tree refs; flex/priority billed as standard | 3 | 2 | [Kong `service_tier_factor`](https://developer.konghq.com/ai-gateway/model-cost-management/) | Same `cost_usd` path as #411; 402 before dispatch | **Filed [#430](https://github.com/naveenreddyalka/daari/issues/430)** (P2) |
| 2 | **Anthropic thinking blocks discarded** — `content_to_text` ignores `thinking`; L6 replay has no signed chain | 3 | 2 | Kong empty-thinking filter + Anthropic Messages | Local hops stay text-only; only L6 Anthropic needs signatures | **Filed [#431](https://github.com/naveenreddyalka/daari/issues/431)** (P2) |
| 3 | **Circuit state invisible** — `/ready` backends omit `breaker.state`; `/v1/daari/stats` is tier counts only | 3 | 1 | (ops gap, daari-specific) | Breaker already in-process (#109/#170) | **Filed [#432](https://github.com/naveenreddyalka/daari/issues/432)** (P2) |
| 4 | **No Batch API** — eval/agent backfills have no `/v1/batches` | 4 | 3 | OpenRouter Batch; LiteLLM e2e batch | Idle L3–L5 overnight at $0; MCP Tasks is the store | **Filed [#433](https://github.com/naveenreddyalka/daari/issues/433)** (P2) |
| 5 | **Anthropic cache write TTL unpriced** — 1h write is 2× 5m; we set ephemeral only | 2 | 2 | Kong `cache_write_cost_list` | Admission estimate before the expensive write | **Filed [#434](https://github.com/naveenreddyalka/daari/issues/434)** (P3) |
| 6 | **Percentile-TTFT routing** — LiteLLM v1.102-dev | 2 | 3 | LiteLLM `-dev` | Need `daari profile` histograms first | Watch |
| 7 | **MCP agent identity** — SEP-1933 still draft | 3 | 3 | MCP Tier-1 SDKs | `secret://oauth` ready | Watch |
| 8 | **SOC 2 / Gemini / A2A / admin UI / off-peak / `/v1/images` / WIF** | 2–3 | 2–5 | Kong / LiteLLM | No new client demand | Watch / non-goal |

09-11 morning rows #418–#422 shipped and are pruned. HITL brew #373 done.

Open backlog after this run:
[#430](https://github.com/naveenreddyalka/daari/issues/430)–[#433](https://github.com/naveenreddyalka/daari/issues/433) (P2),
[#434](https://github.com/naveenreddyalka/daari/issues/434) (P3).

---

## Path to enterprise-grade — next 5 milestones

1. **Honest service-tier billing** ([#430](https://github.com/naveenreddyalka/daari/issues/430)).
2. **Extended-thinking L6 fidelity** ([#431](https://github.com/naveenreddyalka/daari/issues/431)).
3. **Visible circuits** ([#432](https://github.com/naveenreddyalka/daari/issues/432)).
4. **Local batch drain** ([#433](https://github.com/naveenreddyalka/daari/issues/433)).
5. **Cache-TTL write rates** ([#434](https://github.com/naveenreddyalka/daari/issues/434)) when Claude Code catalogs use 1h.

---

## Changelog

- **2026-09-11 late** — Morning refill #418–#422 + brew #373 shipped; backlog
  empty. Outward: Kong service-tier + cache-TTL write pricing; LiteLLM
  1.102-dev TTFT watch. Inward verified: no `service_tier`; thinking blocks
  dropped; `/ready` omits circuit; no `/v1/batches`; ephemeral-only cache
  write. Filed [#430](https://github.com/naveenreddyalka/daari/issues/430)–[#433](https://github.com/naveenreddyalka/daari/issues/433)
  (P2) and [#434](https://github.com/naveenreddyalka/daari/issues/434) (P3).
- **2026-09-11 pm** — No-delta cron after morning scan; backlog already fed.
- **2026-09-11** — Filed #418–#422 (LiteLLM harness-aware headline).
- **2026-09-10** — Filed #409–#412; `AUTODEV_GH_TOKEN` set.
- **2026-09-09 evening / pm / day** — #397–#401, #385–#389, #374–#378.
- **2026-09-08→08-28** (condensed) — Park, labeler, Apache 2.0, this PRD.
