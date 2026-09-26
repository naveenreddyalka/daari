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

## Where daari stands (verified in-tree, 2026-09-26)

**Loop velocity.** Everything filed 2026-09-25 (all eleven issues across three
runs) merged by 14:08 UTC today: SSO bearer governance, graceful shutdown,
cached-token + per-modality metrics, request-time team membership,
model_group budgets, team model_max_budget, config ownership, pre-auth header
policy, doctor moderations/rerank probes, Anthropic moderations ingress,
images edits pins. Backlog at scan start: empty of feature work.

**Outward movers today.** Flat on gateways: LiteLLM stable bar **v1.102.1**
(v1.103 never went stable; v1.104.0-dev.2 signals a native-Rust dispatch
foundation, MCP OAuth token-exchange hardening, `gen_ai.conversation.id`
OTel). Portkey **v2.25.0**, Kong **2.1.0**, vLLM **0.30.0**, OpenRouter
(08-19), MCP blog (08-22) all unchanged. Ollama **0.34.4** stable /
0.40.0-rc0 watch. The movement is **provider-side**: OpenAI September platform
changes make GPT-6 Astra reject custom `temperature`/`top_p`/`logprobs` and
require the **Responses API for tool calling**; new `/v1/responses/compact`
endpoint; async tool calling + WebSocket mid-turn steering; prompt-cache
diagnostics GA. Anthropic ships cache-preserving mid-conversation
`role:"system"` messages (per-message `output_config.effort`, inline
`tool_addition` blocks) and cache diagnostics beta.

**Inward theme: agent-surface fidelity + operate-and-comply.** Verified with
file:line evidence: frontier `_openai_payload` is model-blind (always sends
temperature, tools over `/chat/completions` — now a live astra breakage);
Responses ingress skips `reasoning` items (`responses.py` ~L124) and never
emits them; retention is time-based only with zero subject-erasure path; no
full-state backup/restore CLI (keys export is the only slice); spend rows
lack `user_id` so team×member chargeback needs hand joins.

---

## Scored gap table

| # | Gap | Impact | Effort | Who does it best today | Why daari wins local-first | Action |
|---|-----|:--:|:--:|------------------------|----------------------------|--------|
| 1 | **Frontier param compat for gpt-6-astra** — temperature/top_p/logprobs always sent; tools on chat completions now unsupported upstream | 5 | 2 | LiteLLM per-model supported_params | Router knows the model; strip + warn via existing `daari_meta` contract, Apache-2.0 core | Filed — P1 |
| 2 | **Subject erasure (GDPR/offboarding)** — retention is time-window only; no `erase --key/--team/--user` across stores | 5 | 3 | (nobody ships it as one primitive) | All data on-box → verifiable one-command erasure no SaaS can match | Filed — P2 |
| 3 | **Full-state backup/restore + DR runbook** — no `daari backup`; keys export is the only covered store; no pg_dump docs | 4 | 3 | managed cloud gateways (implicitly) | Self-hosted must own DR; versioned archive + restore drill | Filed — P2 |
| 4 | **Spend `user_id` + team×member rollup** — spend rows have key/team/client only; usage has users but no team join | 4 | 2 | LiteLLM per-member org spend | Chargeback = local query; caps + attribution on the same subject | Filed — P2 |
| 5 | **Responses reasoning-item replay** — ingress drops `type:"reasoning"`; chained turns lose reasoning context | 4 | 3 | OpenAI direct | Local thinking models get the same multi-turn continuity; tier hops keep the chain | Filed — P2 |
| 6 | Responses streaming resume (`GET ?stream=true&starting_after=`) | 3 | 3 | OpenAI direct | Store already holds events | Watch — file on client ask |
| 7 | Hosted Responses tools (`web_search`, `mcp`) accepted silently — no support, no 400 | 3 | 2 | LiteLLM passthrough | Honesty pattern exists (`include` 400s) | Watch — fold into next Responses slice |
| 8 | `/v1/responses/compact` (OpenAI Sept 2026) | 3 | 3 | OpenAI direct | Compact with a **local** model — pay $0 for context maintenance | Watch — file on client demand |
| 9 | Anthropic mid-conversation system fidelity — `hoist_system_messages` (anthropic.py ~L310) destroys cache-preserving appended system turns / `output_config.effort` / `tool_addition` on Anthropic-native L6 egress | 3 | 3 | Anthropic direct | Skip hoist for anthropic egress; hoist only for local llama templates | Watch — Fable 5.1 features still beta-headed |
| 10 | Org construct above teams; per-member caps on shared team keys | 3 | 4 | LiteLLM org→team→member | Flat teams fine until multi-BU buyer | Watch — demand-triggered |
| 11 | Policy-sync drift detection (last-applied hash, `policy-status` probe) | 3 | 2 | Kong CP/DP version gating | Fleet honesty | Watch — file on fleet ask |
| 12 | Batches + cache absent from `prune_all` windows | 3 | 1 | — | Retention completeness | Watch — small; next hygiene slice |
| 13 | Prompt-cache fields (`prompt_cache_key`/`retention`) silently ignored on Responses | 3 | 2 | OpenAI direct | Forward on L6; `dropped_params` locally | Watch |
| 14 | WS agent controls (mid-turn steering, async tools), Agents API, `/v1/decisions`, `/v1/ocr`, WIF, A2A, MCP live sessions, SOC 2, admin UI | 2–4 | 3–5 | OpenAI / Portkey / LiteLLM | Demand-triggered | Watch |

Pruned this run: all eleven 09-25 rows (shipped and closed); images L6 rows
(shipped 09-25/09-26). Verified-fine, do not re-file: Responses background
mode + cancel + `store=false` + `previous_response_id` chain +
`/v1/responses/input_tokens` (responses.py, tenancy tests); end-user usage
attribution + `user_daily_usd_cap`; keys export/import; request-log
retention in `prune_all`.

---

## Path to enterprise-grade — next 5 milestones

1. **Ship model-aware frontier compatibility** — the router must never send a
   payload the provider documents as unsupported (astra P1), with the same
   dropped-params honesty local tiers already have.
2. **Comply-and-operate primitives** — subject erasure and full-state
   backup/restore turn "local-first" into auditable compliance wins instead
   of operational liabilities.
3. **Close the chargeback loop** — user dimension on spend rows joins the
   existing end-user usage ledger to teams; attribute, report, and cap the
   same subject.
4. **Responses as the agent surface** — reasoning replay now; streaming
   resume, hosted-tool honesty, compact, and prompt-cache fields as the
   follow-on slices (rows 6–8, 13).
5. **Anthropic Fable 5.1 fidelity** — preserve mid-conversation system
   semantics on Anthropic-native egress once the beta features harden
   (row 9).

Compliance non-goals (WIF, A2A, SOC 2 program, admin UI, Realtime/WS) stay
deferred until buyer demand.

---

## Changelog

- **2026-09-26 (agent-surface fidelity + operate-and-comply)** — Outward flat
  on gateways (LiteLLM bar v1.102.1, Portkey v2.25.0, Kong 2.1.0, vLLM
  0.30.0 unchanged); the movers are provider-side: OpenAI September changes
  (astra param rejections, tools-require-Responses, `/responses/compact`,
  WS steering) and Anthropic mid-conversation system messages. Inward audit
  (Responses depth, org/spend hierarchy, DR, compliance purge): filed five —
  astra frontier param compat (P1), subject erasure, backup/restore + DR
  runbook, spend user_id + team rollup, Responses reasoning replay. New
  watch: streaming resume, hosted-tool honesty, compact, hoist-vs-Fable-5.1,
  policy drift, batches/cache retention, prompt-cache fields.

- **2026-09-25 (three runs: images layer → identity/shutdown/tokens →
  FinOps/operator honesty)** — Fifteen issues filed across the day; all
  merged by 2026-09-26 14:08.

- **2026-09-24 → 09-15 and earlier** — Condensed: non-chat endpoint parity;
  modality + client-contract honesty; facade/Responses shapes; data-plane
  efficiency; governance secondary ingress; fleet-auth; Batch/Files; Apache
  2.0; this PRD's creation (2026-08-28).
