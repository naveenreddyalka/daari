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

## Where daari stands (verified in-tree, 2026-09-27 late)

**Loop velocity.** Morning refresh already filed fleet-governance gaps
(compact meta, erasure completeness, backup catalog honesty, spend `user_id`
modalities, param-compat depth). Those remain open on the backlog; this late
run does not re-file them.

**Outward (re-checked).** LiteLLM stable bar still **v1.102.1** (OCR + stream
guardrails + gateway reliability); newest non-prerelease pins include
v1.100.3 / v1.101.2; **v1.104.0-dev.2** keeps the OTel v2
`gen_ai.conversation.id` signal. Portkey enterprise changelog publicly tops
at **v2.20.0** (correcting the morning pin that read v2.25.0 off a stale
page). Kong AI Gateway **2.1.0**. vLLM **0.30.0**. Ollama **0.34.4** stable /
**0.40.0-rc0** (MLX) watch. OpenRouter changelog last 08-19.

**Inward theme: session-grade observability + DR depth + fleet install
parity.** Code audit after the morning wave: `RequestMeta.session_id` is
first-class for savings/affinity but never reaches OTel as
`gen_ai.conversation.id`; backup still emits plaintext tarballs and only
*hints* at `pg_dump` instead of embedding dumps when the binary is present;
Helm wires Redis/Postgres/OTLP but not `routing.session_affinity` or
`enterprise.policy_sync_*`; hermetic benches skip the new Responses
compact/resume store hot paths.

---

## Scored gap table

| # | Gap | Impact | Effort | Who does it best today | Why daari wins local-first | Action |
|---|-----|:--:|:--:|------------------------|----------------------------|--------|
| 1 | **OTel `gen_ai.conversation.id`** — `session_id` never stamped on GenAI spans | 4 | 1 | LiteLLM OTel v2 / OTel GenAI semconv | Same session view as cloud gateways; id already at the edge | Filed — P1 ([#1175](https://github.com/naveenreddyalka/daari/issues/1175)) |
| 2 | **Encrypted backup archives** — plaintext `.tar.gz` holds keys/spend/traces | 4 | 2 | pgBackRest / cloud KMS wraps | One-command encrypted DR via openssl/age CLI | Filed — P2 ([#1176](https://github.com/naveenreddyalka/daari/issues/1176)) |
| 3 | **Embed `pg_dump` when present** — fleet DB bytes stay outside the archive | 4 | 2 | Postgres-native tooling | Single artifact when client tools exist; hint-only fallback | Filed — P2 ([#1177](https://github.com/naveenreddyalka/daari/issues/1177)) |
| 4 | **Helm session affinity + policy-sync** — multi-replica knobs are env-only | 3 | 1 | Kong / Portkey installers | Chart parity turns fleet features on without reverse-engineering env | Filed — P2 ([#1178](https://github.com/naveenreddyalka/daari/issues/1178)) |
| 5 | **Hermetic benches for compact + stream-resume store** — no ceiling on new hot paths | 3 | 2 | — (in-tree only) | Catch SQLite/PG store regressions without Ollama | Filed — P2 ([#1179](https://github.com/naveenreddyalka/daari/issues/1179)) |
| 6 | Compact/Responses governance parity (empty compact meta; model_max_budget chat-only; rate-family subpaths) | 5 | 2 | LiteLLM | Same fences on every surface | Open — morning P1 |
| 7 | Erasure fleet completeness (Redis L0/L1, PG batches, spend user_id, traces) | 5 | 2 | — | Provable erasure across recommended stores | Open — morning P1 |
| 8 | Backup catalog honesty (PG batches/files, rotated logs, hot-restore interlock) | 4 | 2 | Postgres-native tooling | Honest manifest for self-hosted DR | Open — morning P2 |
| 9 | Spend `user_id` on every modality + Responses `user` | 4 | 2 | LiteLLM end-user tracking | Complete team×member chargeback | Open — morning P2 |
| 10 | Param-compat depth (config table, Anthropic egress, streamed warnings) | 3 | 2 | LiteLLM supported_params | Operator hotfix without a release train | Open — morning P2 |
| 11 | Anthropic beta fidelity (`output_config.effort`, `tool_addition`) | 3 | 3 | Anthropic direct | Hoist fix landed; betas still hardening | Watch |
| 12 | Native `/v1/ocr` (LiteLLM 1.102 OCR layer) | 3 | 4 | LiteLLM | Local OCR tier before frontier | Watch — demand |
| 13 | Org above teams; MCP inbound OAuth / resource metadata; WS/A2A/SOC2/admin UI | 2–4 | 3–5 | Portkey / OpenAI / LiteLLM | Demand-triggered | Watch |

Pruned this run: nothing newly shipped since the morning refresh (backlog
still working the governance/fleet slice). Verified-fine, do not re-file:
streaming output guardrails already have `IncrementalOutputScanner`;
percentile TTFT preference shipped; doctor already warns on
session_affinity-without-redis and missing recent backups; `/v1/responses`
create path applies auth claims (compact does not — covered by morning P1).

---

## Path to enterprise-grade — next 5 milestones

1. **Session-grade observability** — `gen_ai.conversation.id` from the
   session header so multi-turn agent loops are one query in any OTel backend.
2. **Every surface governs like chat** — finish the morning governance slice
   (compact meta, model budgets, rate families).
3. **Fleet-true compliance + DR** — erasure across Redis/Postgres; honest
   catalogs; encrypted archives; optional embedded `pg_dump`.
4. **Chargeback + install parity** — `user_id` on every modality; Helm knobs
   for affinity and policy-sync so fleets can turn features on from values.
5. **Then depth on demand** — Anthropic betas, OCR, MCP inbound OAuth,
   org hierarchy, decisions API as buyers surface.

Compliance non-goals (WIF, A2A, SOC 2 program, admin UI, Realtime/WS) stay
deferred until buyer demand.

---

## Changelog

- **2026-09-27 late (session OTel + DR depth + Helm parity)** — Outward flat;
  Portkey public pin corrected to v2.20.0. Filed OTel
  `gen_ai.conversation.id` (P1), encrypted backups, embedded `pg_dump`, Helm
  session-affinity/policy-sync, hermetic benches for compact/resume store
  (P2s). Morning fleet-governance issues remain open; not re-filed.

- **2026-09-27 (fleet-backend completeness + governance consistency)** —
  Whole 09-26 table drained overnight. Audited new primitives at fleet grade;
  filed compact/Responses governance, erasure completeness, backup catalog
  honesty, spend `user_id` modalities, param-compat depth.

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
