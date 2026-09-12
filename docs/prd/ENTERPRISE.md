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

## Where daari stands (verified in-tree, 2026-09-12)

**Another same-day drain.** The 09-11 late refill #430–#434 all merged overnight
(PRs #436–#440): service-tier pricing, thinking-block replay, circuit state on
`/ready`, the Batch API first slice, and cache-TTL write rates. Backlog and open
PRs were both empty at run start.

**Positioning:** outward is quiet — LiteLLM stable still v1.100.1 (v1.102 still
`-dev`), Kong at 2.0.3 since 08-31, Portkey changelog unmoved post-PANW,
OpenRouter changelog last entry 08-19, SEP-1933 still draft. Today's value is
inward: the #433 Batch slice shipped fast but ungoverned — batch items run with
an **empty `RequestMeta`**, bypassing per-key tier caps, `no_frontier`, budgets,
user attribution, and guardrails. That plus the missing Files API is this run's
refill.

---

## Scored gap table

| # | Gap | Impact | Effort | Who does it best today | Why daari wins local-first | Action |
|---|-----|:--:|:--:|------------------------|----------------------------|--------|
| 1 | **Batch bypasses governance** — items route with empty `RequestMeta`: no key identity, tier caps, budgets, guardrails, or spend attribution | 5 | 2 | LiteLLM end-to-end batch billing (v1.99) | Identity already resolved at create time; snapshot it onto the job | **Filed [#441](https://github.com/naveenreddyalka/daari/issues/441)** (P1) |
| 2 | **No `/v1/files`** — `input_file_id` fails validation, `output_file_id` always null; stock OpenAI SDK batch scripts can't run | 4 | 2 | OpenRouter `/files`; LiteLLM files proxy | JSONL blobs on local disk, no object store needed | **Filed [#442](https://github.com/naveenreddyalka/daari/issues/442)** (P2) |
| 3 | **No one-command client onboarding** — 8 manual docs recipes; server-side `daari onboard` only | 4 | 2 | LiteLLM `lite configure claude` (v1.102-dev) | Same machine as the client: write config + verify loop directly | **Filed [#445](https://github.com/naveenreddyalka/daari/issues/445)** (P2) |
| 4 | **Batch jobs are in-process only** — restart loses `in_progress` jobs despite 24h window; invisible across Helm's 2 replicas | 3 | 2 | (durability is table stakes) | SQLite pattern already in keys/audit stores | **Filed [#443](https://github.com/naveenreddyalka/daari/issues/443)** (P2) |
| 5 | **Batch drain contends with interactive traffic** — "idle tiers" pitch, but worker drains immediately | 3 | 2 | (daari-specific differentiator) | Both queues in one process; cloud gateways can't see local GPU contention | **Filed [#444](https://github.com/naveenreddyalka/daari/issues/444)** (P2) |
| 6 | **Percentile-TTFT routing** — LiteLLM v1.102-dev only | 2 | 3 | LiteLLM `-dev` | Need latency histograms first | Watch |
| 7 | **MCP agent identity** — SEP-1933 still draft (re-checked 09-12) | 3 | 3 | MCP Tier-1 SDKs | `secret://oauth` ready | Watch |
| 8 | **SOC 2 / Gemini facade / A2A / admin UI / off-peak / `/v1/images` / WIF / streamed `usage.cost`** | 2–3 | 2–5 | Kong / LiteLLM | No new client demand | Watch / non-goal |

Pruned this run: #430–#434 rows (all shipped 09-11/09-12); multi-JWKS watch row
(shipped as #422 / PR #429).

Open backlog after this run:
[#441](https://github.com/naveenreddyalka/daari/issues/441) (P1),
[#442](https://github.com/naveenreddyalka/daari/issues/442)–[#445](https://github.com/naveenreddyalka/daari/issues/445) (P2).

---

## Path to enterprise-grade — next 5 milestones

1. **Close the batch governance hole** ([#441](https://github.com/naveenreddyalka/daari/issues/441)) — a governed gateway cannot ship an ungoverned endpoint.
2. **Stock-SDK batch flow** ([#442](https://github.com/naveenreddyalka/daari/issues/442)) — files in, files out, unmodified OpenAI scripts.
3. **One-command client onboarding** ([#445](https://github.com/naveenreddyalka/daari/issues/445)) — the top-of-funnel for every IDE client.
4. **Durable batches** ([#443](https://github.com/naveenreddyalka/daari/issues/443)) — overnight drain must survive a redeploy.
5. **Idle-yield drain** ([#444](https://github.com/naveenreddyalka/daari/issues/444)) — make "batches run when your machine is idle" literally true.

---

## Changelog

- **2026-09-12** — 09-11 late refill #430–#434 all merged overnight (#436–#440);
  backlog empty. Outward quiet (LiteLLM stable v1.100.1, Kong 2.0.3, Portkey/
  OpenRouter unmoved, SEP-1933 draft). Inward: Batch slice audit found the
  governance bypass (empty `RequestMeta` in `_execute_batch_chat_body`), missing
  `/v1/files`, in-process-only `BatchStore`, no idle-yield; plus no
  `daari configure <client>` (LiteLLM `lite configure claude` parity). Filed
  [#441](https://github.com/naveenreddyalka/daari/issues/441) (P1),
  [#442](https://github.com/naveenreddyalka/daari/issues/442)–[#445](https://github.com/naveenreddyalka/daari/issues/445)
  (P2). Multi-JWKS watch row resolved (#422 shipped).
- **2026-09-11 late** — Filed #430–#434 (Kong service-tier/cache-TTL parity,
  circuit visibility, Batch API).
- **2026-09-11 pm** — No-delta cron after morning scan; backlog already fed.
- **2026-09-11** — Filed #418–#422 (LiteLLM harness-aware headline).
- **2026-09-10** — Filed #409–#412; `AUTODEV_GH_TOKEN` set.
- **2026-09-09 evening / pm / day** — #397–#401, #385–#389, #374–#378.
- **2026-09-08→08-28** (condensed) — Park, labeler, Apache 2.0, this PRD.
