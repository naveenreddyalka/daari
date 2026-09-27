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

## Where daari stands (verified in-tree, 2026-09-27)

**Loop velocity.** The entire 2026-09-26 scored table drained in under 24h:
astra param compat, subject erasure, full-state backup/restore, spend
`user_id` + team chargeback, reasoning-item replay, hosted-tool 400s,
batches+cache in `prune_all`, Responses prompt-cache fields, policy-sync
drift hash + `policy-status` (+ doctor tip), streaming resume
(`starting_after` + `Last-Event-ID` + `sequence_number`), and
`/v1/responses/compact` — plus the Anthropic mid-conversation fix (hoist now
happens only in the local Ollama executor, so Anthropic/frontier egress keeps
system-turn layout).

**Outward (re-checked, flat).** LiteLLM stable bar **v1.102.1**
(v1.104.0-dev.2 = prices/fixes; notable dev signal: `gen_ai.conversation.id`
on OTel v2 spans). Portkey enterprise gateway tops at **v2.25.0**
(2026-09-24 — correcting the prior refresh's v2.20.0 note, which read a stale
page). Kong AI Gateway **2.1.0** (09-22). vLLM **0.30.0**, Ollama **0.34.4**
stable / **0.40.0-rc0** (MLX-on-Apple-Silicon) watch. OpenRouter changelog
last 08-19; MCP blog last 08-22.

**Inward theme: fleet-backend completeness + governance consistency of the
new primitives.** A code audit of the 24h wave found the features are
single-node/SQLite-complete but leak on the backends daari itself recommends
for fleets, and the new surfaces don't all govern like chat. Verified with
file:line evidence: compact routes with an **empty `RequestMeta`** (no tenant
fences, no attribution); `model_max_budget` enforced on chat only; erasure
misses Redis L0/L1, Postgres batches, `user_id` spend rows, and traces;
backup's catalog misreports Postgres-backed batches/files and skips rotated
request logs; param-compat is astra-hardcoded, skips Anthropic egress, and
drops its honesty warnings on streams.

---

## Scored gap table

| # | Gap | Impact | Effort | Who does it best today | Why daari wins local-first | Action |
|---|-----|:--:|:--:|------------------------|----------------------------|--------|
| 1 | **Compact/Responses governance parity** — compact has empty meta (frontier-escape for capped keys); `model_max_budget` chat-only; rate families mis-bucket subpaths | 5 | 2 | LiteLLM (meters Responses like chat) | Same per-key fences on every surface, incl. $0 local compaction | Filed — P1 ([#1169](https://github.com/naveenreddyalka/daari/issues/1169)) |
| 2 | **Erasure fleet completeness** — Redis L0/L1, PG batches, `user_id` spend rows, traces all survive erase | 5 | 2 | — (nobody does local-first erasure) | Provable erasure across every store daari recommends | Filed — P1 ([#1170](https://github.com/naveenreddyalka/daari/issues/1170)) |
| 3 | **Backup catalog honesty** — PG batches/files misreported as local; rotated logs skipped; no hot-restore interlock | 4 | 2 | Postgres-native tooling | Honest manifest is the point of self-hosted DR | Filed — P2 ([#1171](https://github.com/naveenreddyalka/daari/issues/1171)) |
| 4 | **Spend `user_id` beyond chat** — all modality binders + `ResponsesRequest.user` missing | 4 | 2 | LiteLLM end-user tracking | One chargeback dimension across every metered dollar | Filed — P2 ([#1172](https://github.com/naveenreddyalka/daari/issues/1172)) |
| 5 | **Param-compat depth** — config-driven table, Anthropic egress, streamed dropped-param warnings | 3 | 2 | LiteLLM supported_params | Operator hotfix without a release train; honesty on streams | Filed — P2 ([#1173](https://github.com/naveenreddyalka/daari/issues/1173)) |
| 6 | Backup embeds Postgres data (run `pg_dump` when client tools present) + archive encryption | 4 | 3 | pgBackRest et al. | One-command DR incl. fleet DBs | Watch — runbook covers today |
| 7 | Org construct above teams; per-member caps on shared team keys | 3 | 4 | LiteLLM org→team→member | Flat teams fine until multi-BU | Watch — demand |
| 8 | Anthropic beta fidelity (per-message `output_config.effort`, inline `tool_addition`) | 3 | 3 | Anthropic direct | Hoist fix landed; betas still hardening | Watch |
| 9 | Native `/v1/ocr` (LiteLLM 1.102 OCR layer) | 3 | 4 | LiteLLM | Local OCR tier before frontier | Watch — demand |
| 10 | WS agent controls, Agents API, WIF, A2A, MCP live sessions, `/v1/decisions` typed judgments, SOC 2, admin UI | 2–4 | 3–5 | OpenAI / Portkey / LiteLLM | Demand-triggered | Watch |

Pruned this run (shipped since 2026-09-26 late): hosted-tool 400s, batches +
cache in `prune_all`, prompt-cache fields, policy drift/`policy-status`,
streaming resume, `/v1/responses/compact`, Anthropic hoist scope, astra param
compat, erasure/backup/spend-`user_id` v1 slices, reasoning replay.
Verified-fine this audit, do not re-file: resume is tenancy-scoped +
Postgres-aware + terminal-only (409); header policy is pre-auth with
health/ready/metrics bypass; team `model_max_budget` merges team→key and
402s at request time on chat; shared `/v1/*` middleware (auth, budgets, rate
limits, admission) covers responses + compact; VK backup rows carry hashes,
not plaintext; erasure keeps audit (hash chain) and logs `compliance.erase`.

---

## Path to enterprise-grade — next 5 milestones

1. **Every surface governs like chat** — compact/Responses meta, model
   budgets, and rate families converge on one enforcement path.
2. **Fleet-true compliance** — erasure and backup that are honest about
   Redis/Postgres, not just single-node SQLite.
3. **Chargeback closes end-to-end** — `user_id` on every metered modality so
   team×member spend is complete.
4. **Provider-drift resilience** — config-driven param compat with honesty
   warnings on streams; Anthropic egress included.
5. **Then depth on demand** — Postgres-embedding backup, org hierarchy,
   Anthropic betas, OCR, decisions API as buyers surface.

Compliance non-goals (WIF, A2A, SOC 2 program, admin UI, Realtime/WS) stay
deferred until buyer demand.

---

## Changelog

- **2026-09-27 (fleet-backend completeness + governance consistency)** —
  Whole 09-26 table drained overnight (11 feature PRs + docs). Outward flat;
  Portkey pin corrected back to v2.25.0. Audited the new primitives at
  fleet grade: filed compact/Responses governance parity (P1), erasure
  fleet completeness (P1), backup catalog honesty, spend `user_id` across
  modalities, param-compat depth (P2s). Baseline suite 2827 passed.

- **2026-09-26 (two runs: agent-surface fidelity; Responses honesty +
  retention + fleet visibility)** — Filed ten across astra compat, erasure,
  backup, chargeback, reasoning replay, hosted-tool 400s, prune_all,
  prompt-cache fields, drift hash, streaming resume. All merged by 09-27.

- **2026-09-25 (three runs)** — Fifteen issues across images / identity /
  FinOps; all merged by 2026-09-26 14:08.

- **2026-09-24 → 09-15 and earlier** — Condensed: non-chat endpoint parity;
  modality + client-contract honesty; facade/Responses shapes; data-plane
  efficiency; governance secondary ingress; fleet-auth; Batch/Files; Apache
  2.0; this PRD's creation (2026-08-28).
