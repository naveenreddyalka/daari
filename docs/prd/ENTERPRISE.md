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

## Where daari stands (verified in-tree, 2026-09-26 late)

**Loop velocity.** Morning refresh already filed five issues (astra param compat,
subject erasure, backup/restore, spend `user_id`, Responses reasoning replay)
and merged the companion PRD PR. This late run promotes the next Responses /
retention / fleet-honesty watch rows so the backlog stays stocked while those
ship.

**Outward movers (re-checked).** LiteLLM stable still **v1.102.1**; **v1.104.0-dev.2**
keeps the native-Rust / OCR / streaming-guardrail trajectory (no new stable).
Portkey enterprise changelog tops at **v2.20.0** (prior scan's v2.25.0 pin was
stale — corrected here). Kong AI Gateway **2.0 GA** (2026-09-01) unchanged at
scan depth. vLLM **0.30.0**, Ollama **0.34.4** stable / **0.40.0-rc0** (Apple
Silicon MLX-by-default) watch. OpenAI surface still drives the agent gap:
`/v1/responses/compact`, `GET …?stream=true&starting_after=`, `prompt_cache_key`
/ retention, hosted tools (`web_search`, `mcp`).

**Inward theme: Responses honesty + retention completeness + fleet visibility.**
Verified: `GET /v1/responses/{id}` ignores `stream`/`starting_after`
(`responses.py` ~L337–341); `responses_tools_to_openai` passes non-function
tool types through (~L139–156) so hosted tools are accepted silently;
`ResponsesRequest` has no `prompt_cache_key`/`prompt_cache_retention` fields
(~L46–68); `prune_all` covers traces/ledger/spend/shadow/tasks/files/responses/
idempotency/request_log/audit but **not** batches or L0/L1 cache
(`retention.py` ~L66–236; `RetentionSettings` has no batches/cache days);
policy sync applies overrides with no last-applied hash or doctor/`policy-status`
probe (`enterprise/policy_sync.py`, CLI `enterprise policy-sync` only).

---

## Scored gap table

| # | Gap | Impact | Effort | Who does it best today | Why daari wins local-first | Action |
|---|-----|:--:|:--:|------------------------|----------------------------|--------|
| 1 | **Hosted Responses tools honesty** — `web_search` / `mcp` / non-function types accepted and forwarded; no 400 | 4 | 2 | LiteLLM passthrough / OpenAI direct | Match existing `include` 400 honesty; fail closed locally | Filed — P2 |
| 2 | **Batches + cache absent from `prune_all`** — no `batches_days` / cache prune window; BatchStore has no prune API | 3 | 1 | — | One retention dial for every on-box store | Filed — P2 |
| 3 | **Responses `prompt_cache_key` / retention** — fields ignored (`extra=allow` keeps them off the declared model) | 4 | 2 | OpenAI direct | Forward on L6; surface `dropped_params` on local tiers | Filed — P2 |
| 4 | **Policy-sync drift detection** — no last-applied hash, no `policy-status` / doctor probe | 3 | 2 | Kong CP/DP version gating | Fleet operators see drift without scraping logs | Filed — P2 |
| 5 | **Responses streaming resume** — `GET ?stream=true&starting_after=` unsupported | 3 | 3 | OpenAI direct | Store already holds output; reconnect agents without re-run | Filed — P3 |
| 6 | Frontier param compat for gpt-6-astra (temperature/tools transport) | 5 | 2 | LiteLLM supported_params | Model-aware strip + `daari_meta` | Open (morning) |
| 7 | Subject erasure / full-state backup / spend `user_id` / reasoning replay | 4–5 | 2–3 | (mixed) | Local-first compliance + chargeback + agent fidelity | Open (morning) |
| 8 | `/v1/responses/compact` (local model compaction) | 3 | 3 | OpenAI direct | Compact with a **local** model — $0 context maintenance | Watch |
| 9 | Anthropic mid-conversation system fidelity — `hoist_system_messages` (~L310) vs Fable 5.1 cache-preserving system turns | 3 | 3 | Anthropic direct | Skip hoist for anthropic egress | Watch — beta still hardening |
| 10 | Org above teams; per-member caps on shared team keys | 3 | 4 | LiteLLM org→team→member | Flat teams fine until multi-BU | Watch |
| 11 | Native `/v1/ocr` (LiteLLM 1.102 OCR layer) | 3 | 4 | LiteLLM | Local OCR tier before frontier | Watch — demand |
| 12 | WS agent controls, Agents API, WIF, A2A, MCP live sessions, SOC 2, admin UI | 2–4 | 3–5 | OpenAI / Portkey / LiteLLM | Demand-triggered | Watch |

Pruned this run: none newly shipped since morning refresh. Morning-filed rows
kept as "Open (morning)" so the table stays the single gap source of truth.
Verified-fine, do not re-file: Responses background + cancel + `store=false` +
`previous_response_id` + `/v1/responses/input_tokens`; end-user usage caps;
keys export/import; request-log retention in `prune_all`.

---

## Path to enterprise-grade — next 5 milestones

1. **Ship model-aware frontier compatibility** — never send a payload the
   provider documents as unsupported (astra), with dropped-params honesty.
2. **Comply-and-operate primitives** — subject erasure and full-state
   backup/restore turn local-first into auditable wins.
3. **Close the chargeback loop** — `user_id` on spend joins the end-user
   usage ledger to teams.
4. **Responses as the agent surface** — reasoning replay (open); then hosted
   tool honesty, prompt-cache fields, streaming resume, and compact
   (this run + watch).
5. **Fleet policy honesty** — drift hash + `policy-status` so org sync is
   observable; Anthropic mid-conversation fidelity once betas harden.

Compliance non-goals (WIF, A2A, SOC 2 program, admin UI, Realtime/WS) stay
deferred until buyer demand.

---

## Changelog

- **2026-09-26 late (Responses honesty + retention + fleet visibility)** —
  Re-checked outward: LiteLLM bar v1.102.1 (+ v1.104.0-dev.2), Portkey
  enterprise **v2.20.0** (corrected), Kong 2.0 GA, vLLM 0.30.0, Ollama
  0.34.4 / 0.40.0-rc0. Promoted five watch rows into filings: hosted-tool
  400s, batches+cache in `prune_all`, Responses prompt-cache fields,
  policy-sync drift/`policy-status`, streaming resume (`starting_after`).
  Compact, Anthropic hoist, OCR, org hierarchy remain watch.

- **2026-09-26 (agent-surface fidelity + operate-and-comply)** — Provider-side
  movers (astra param rejections, tools-require-Responses, compact, WS
  steering). Filed five: astra frontier param compat (P1), subject erasure,
  backup/restore + DR runbook, spend user_id + team rollup, Responses
  reasoning replay.

- **2026-09-25 (three runs)** — Fifteen issues across images / identity /
  FinOps; all merged by 2026-09-26 14:08.

- **2026-09-24 → 09-15 and earlier** — Condensed: non-chat endpoint parity;
  modality + client-contract honesty; facade/Responses shapes; data-plane
  efficiency; governance secondary ingress; fleet-auth; Batch/Files; Apache
  2.0; this PRD's creation (2026-08-28).
