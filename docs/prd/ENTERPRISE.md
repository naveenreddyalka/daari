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

## Where daari stands (verified in-tree, 2026-09-24)

Yesterday's ten filings fully drained overnight: both parameter-fidelity sets,
the facade `think`/`format`/`keep_alive` contract, Responses-native shapes,
`x-daari-dropped-params`, MCP empty resources/prompts lists, multimodal cache
keys (L0 + L1 agent-prefix), **`/v1/moderations`**, **`/v1/rerank`**, and
OpenRouter `region_pin` host mapping all merged by 14:33 UTC today.

**Outward (this run): flat.** **Ollama v0.34.4 stable 09-23** — single-pass
structured outputs on thinking models is internal; no new API surface, facade
unaffected (watch resolved). **LiteLLM** stable bar stays **v1.102.1**
(v1.101.2 is a 09-24 backport patch; tip still v1.104.0-dev.1). **Portkey
v2.24.0**, **Kong 2.1.0**, **vLLM 0.30.0**, OpenRouter changelog (08-19), and
the MCP blog (08-22 roadmap) all unchanged.

**Inward theme: non-chat endpoint parity (code-verified).** Shared middleware
(auth, budget 402 pre-check, RPM/TPM/RPD, global admission with per-key
priority, budget headers) covers every `/v1/*` route — verified fine. But the
endpoint-level layers diverge: **moderations + rerank** are thin L6
passthroughs with no model-allowlist/`no_frontier` fence, no ledger rows, raw
un-retried POSTs to `slots[0]` only, and no `region_pin`; **ASR frontier
fallback uploads raw audio** without consulting `no_frontier`/`region_pin`;
**guardrails run on chat/MCP only** — embeddings, TTS input, ASR output,
rerank documents, and moderation inputs are unscreened; **cost headers are
chat-only** (modality endpoints meter the ledger but return no
`x-daari-response-cost`).

Verified shipped — pruned from watch: per-key/team model allowlists,
per-request spend export, Postgres virtual keys/teams, Helm
preStop/termination grace, admission-priority CLI, MCP `ttlMs`/`cacheScope`
hints on tools/list, CORS + security-header middleware, ASR/TTS/embeddings
retry wrappers, pooled httpx everywhere including the two new slices.

---

## Scored gap table

| # | Gap | Impact | Effort | Who does it best today | Why daari wins local-first | Action |
|---|-----|:--:|:--:|------------------------|----------------------------|--------|
| 1 | **Moderations + rerank bypass key governance & chargeback** — no allowlist, no `no_frontier`/tier fence, no spend/usage rows; local-only keys burn frontier invisibly | 5 | 2 | LiteLLM / Portkey (catalog-metered) | One set of key claims must govern every route on the box | File ([#1058](https://github.com/naveenreddyalka/daari/issues/1058)) |
| 2 | **Guardrails skip all non-chat endpoints** — embeddings/TTS/ASR/rerank/moderations payloads leave unscreened; ASR fallback ships raw audio past policy | 4 | 3 | Portkey per-route guardrails | In-process policy beside the data, no extra hop; "one policy, every route" | File ([#1059](https://github.com/naveenreddyalka/daari/issues/1059)) |
| 3 | **Moderations/rerank: raw POST, `slots[0]` only** — no `run_upstream` retry, no slot failover, no `region_pin` filter | 3 | 2 | Portkey v2.24 per-attempt retry | Retry policy + slot pool + region filter already built; wire them in | File ([#1060](https://github.com/naveenreddyalka/daari/issues/1060)) |
| 4 | **ASR frontier fallback ignores `no_frontier` + `region_pin`** — raw audio uploads from local-only or region-pinned keys | 4 | 2 | (none — cloud gateways can't promise it) | "Audio never leaves the box unless allowed" is only daari's to keep | File ([#1061](https://github.com/naveenreddyalka/daari/issues/1061)) |
| 5 | **No cost headers on modality responses** — embeddings/audio meter the ledger but FinOps clients keying `x-daari-response-cost` see chat only | 3 | 2 | LiteLLM (stream usage.cost, chat) | $0-local proof on every response, not just chat | File ([#1062](https://github.com/naveenreddyalka/daari/issues/1062)) |
| 6 | Watch queue: MCP live-session visibility (LiteLLM v1.104-dev; file on stable), facade `/api/chat` extra options beyond core set, `daari migrate` CLI / skew guard, Anthropic-native moderations, WIF upstream creds, A2A, SOC 2, admin UI | 2–4 | 2–5 | LiteLLM / Portkey / cloud | Operator or client demand triggers these | Watch |

Pruned this run (shipped): all five 09-23 rows, both 09-23 fidelity sets,
moderations/rerank endpoints themselves, OpenRouter region hosts, ASR/TTS/embed
retry wrappers, model allowlists + spend export, Postgres keys/teams, Helm
graceful rollout, admission-priority CLI, MCP cache hints, CORS/security
headers. Ollama thinking-controls and 0.34.4 structured-output watch rows
resolved (internal-only release).

---

## Path to enterprise-grade — next 5 milestones

1. **One governance plane, every route** — key claims (allowlists,
   `no_frontier`, tier caps, `region_pin`) and ledger attribution enforced on
   moderations, rerank, and the ASR fallback exactly as on chat.
2. **One policy plane, every payload** — input/output guardrails on
   embeddings, audio, rerank, and moderations so "PII stays local" is a
   whole-gateway promise.
3. **Uniform resilience** — `run_upstream` retry + slot failover + region
   filtering on the two remaining raw-POST slices.
4. **Cost transparency everywhere** — `x-daari-response-cost` on modality
   responses, matching ledger rows.
5. **MCP session visibility** — deferred until LiteLLM ships it stable or a
   fleet asks; daari's stateless ingress is otherwise at protocol parity
   (2026-07-28 + cache hints).

Compliance non-goals (WIF, A2A, SOC 2, admin UI) stay deferred until a paying ask.

---

## Changelog

- **2026-09-24 (non-chat endpoint parity)** — Outward flat (Ollama v0.34.4
  stable = internal only; LiteLLM bar v1.102.1; Portkey/Kong/vLLM/OpenRouter
  unchanged). Full overnight drain again — all ten 09-23 filings plus
  moderations/rerank/region-hosts shipped. Audit of the five non-chat
  endpoint families found moderations+rerank second-class (governance,
  metering, retry, residency), guardrails chat/MCP-only, ASR fallback
  claim-blind, cost headers chat-only. Filed five. Pruned eleven shipped
  watch rows incl. Postgres keys/teams, allowlists, spend export, Helm
  rollout, MCP cache hints, CORS.

- **2026-09-23 (two runs: client parameter fidelity; facade + Responses
  shapes)** — Ollama v0.34.3 stable; LiteLLM v1.102.1 backport wave +
  v1.104.0-dev.1. Silent drops across both ingresses (non-stream frontier
  tools, `service_tier`, `strict`, seven-param cluster, Anthropic
  thinking/metadata/top_k), then facade `think`/`format`/`keep_alive`,
  Responses shape mapper, drop header, MCP probe 404s, stream failover
  ceiling. Filed ten across the two runs; all drained by 09-24.

- **2026-09-22 (two runs)** — Data-plane efficiency + stream truncation
  fidelity (pooled httpx, keepalive, `stream_incomplete` + breaker, stream
  host failover, Postgres pool), then correlation + modality resilience
  (X-Request-ID everywhere, MCP cache hints, ASR/TTS/embed retry,
  `input_audio`). Portkey v2.24.0, Kong 2.1.0, vLLM 0.30.0.

- **2026-09-21 (two runs)** — Data-plane hardening + lossless escalation
  (TLS/mTLS, body cap, 401 throttle, frontier tool parity, lifetime budgets),
  then browser/ops + agent SDK knobs (CORS/security headers, safe-method
  rate-limit skip, sampling passthrough, MCP stats, migrate/skew CLI).

- **2026-09-15 → 09-20 and earlier** — Condensed: governance secondary
  ingress + resilience/modality delta; embed/ASR measurement + cache tenancy
  + request lifecycle; soft-budget drain + governance/chargeback theme; loop
  restructure (never-empty refill + scheduled Actions prd run); fleet-auth,
  fleet story, resilience + metering, stored-artifact tenancy, Batch/Files
  API, pricing refresh, session affinity, stall escalation, MCP pagination,
  Apache 2.0 relicense, this PRD's creation (2026-08-28).
