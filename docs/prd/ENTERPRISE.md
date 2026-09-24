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

## Where daari stands (verified in-tree, 2026-09-24 evening)

Morning's non-chat governance set is still open on the backlog (key claims,
guardrails, retry/`region_pin`, ASR fence, modality cost headers). This
second scan does **not** re-file those — it picks the next layer once that
plane is in flight.

**Outward (this run): still flat.** **Ollama v0.34.4** (09-23) unchanged —
structured outputs on thinking models remain internal; facade still silently
drops 0.34 **tool_search** / **response_compaction** (compat tests pin ignore).
**LiteLLM** stable bar **v1.102.1**; tip **v1.104.0-dev.1** (MCP live sessions,
Transcribe passthrough, vault namespaces — file MCP sessions when stable).
**Portkey** product changelog (weekly/**rpw** windows, endpoint-scoped limits,
Agent Gateway) unchanged vs morning; open-source gateway tag still **v1.15.2**.
**Kong AI Gateway 2.0** GA wave + **vLLM 0.30.0** unchanged. No new OpenRouter
API surface.

**Inward theme: missing modality surface + client-contract honesty.** Image
*generation* is the last common OpenAI path with no daari route (vision
*inputs* exist; `POST /v1/images/generations` does not). Idempotency-Key stops
at chat/Responses while embeddings/audio/moderations/rerank double-execute on
SDK retries. Facade 0.34 knobs are accepted then discarded with no
`x-daari-dropped-params`. Budget `normalize_duration` lacks `week`/`rpw`
aliases Portkey templates use (`7d` works; `week` raises). Moderations/rerank
have unit tests only — no gateway-flow integration pins (AGENTS.md bar).

Verified shipped — pruned from watch: morning's ten 09-23 fidelity/facade
filings, moderations/rerank endpoints themselves, OpenRouter region hosts,
`daari migrate` skew guard, facade think/format/keep_alive + /api/show
thinking controls, OTel GenAI baseline (#167).

---

## Scored gap table

| # | Gap | Impact | Effort | Who does it best today | Why daari wins local-first | Action |
|---|-----|:--:|:--:|------------------------|----------------------------|--------|
| 1 | **No `POST /v1/images/generations`** — clients need a second base URL for image gen; chat/embed/audio/moderations/rerank already on-box | 4 | 3 | LiteLLM / Portkey / Kong | One OpenAI root, one key fence, incl. creative workloads | File ([#1064](https://github.com/naveenreddyalka/daari/issues/1064)) |
| 2 | **Idempotency-Key chat/Responses only** — embeddings/audio/moderations/rerank double-bill on retries | 4 | 2 | Portkey / cloud gateways | Tunnel flaps + cold local backends make retries common; chargeback must stay honest | File ([#1065](https://github.com/naveenreddyalka/daari/issues/1065)) |
| 3 | **Facade silently drops Ollama 0.34 tool_search / response_compaction** — worse than talking to Ollama directly | 3 | 2 | Ollama native | Forward on local Ollama hops; declare drops via `x-daari-dropped-params` otherwise | File ([#1066](https://github.com/naveenreddyalka/daari/issues/1066)) |
| 4 | **Budget durations reject `week`/`weekly`/`rpw`** — Portkey FinOps templates fail; only `7d` works | 3 | 1 | Portkey rpw | Alias parity makes migrate-from-Portkey mechanical | File ([#1067](https://github.com/naveenreddyalka/daari/issues/1067)) |
| 5 | **Moderations/rerank lack gateway-flow integration pins** — unit-only; AGENTS.md wants integration for public routes | 3 | 1 | (internal bar) | Keeps thickening L6 slices from regressing OpenAPI/auth/happy-path | File ([#1068](https://github.com/naveenreddyalka/daari/issues/1068)) |
| 6 | In flight (morning): moderations/rerank governance+metering, non-chat guardrails, retry/`region_pin`, ASR `no_frontier`/`region_pin`, modality cost headers | 3–5 | 2–3 | — | One governance/policy/cost plane on every route | In backlog |
| 7 | Watch queue: MCP live-session visibility (LiteLLM v1.104-dev; file on stable), Anthropic-native moderations, endpoint-scoped RPM families, WIF upstream creds, A2A, SOC 2, admin UI | 2–4 | 2–5 | LiteLLM / Portkey / cloud | Operator or client demand triggers these | Watch |

Pruned this run: stale watch rows for migrate CLI, facade core options, and
Ollama thinking-controls (all shipped). Morning non-chat rows stay "in
backlog" rather than re-filed.

---

## Path to enterprise-grade — next 5 milestones

1. **Finish non-chat governance** — morning backlog: allowlists/`no_frontier`/
   ledger on moderations+rerank, guardrails on every payload, ASR claim fence,
   modality cost headers, retry/`region_pin` on the remaining raw POSTs.
2. **Close the OpenAI surface hole** — governed `/v1/images/generations` so
   creative clients share the same local-first key plane.
3. **Retry-safe modality plane** — Idempotency-Key on embeddings/audio/
   moderations/rerank matching chat/Responses.
4. **Honest Ollama facade** — forward or declare 0.34 tool_search /
   response_compaction; stop silent drops.
5. **FinOps alias parity + test bar** — `week`/`rpw` budget windows; integration
   pins on the newest L6 routes.

Compliance non-goals (WIF, A2A, SOC 2, admin UI) stay deferred until a paying ask.

---

## Changelog

- **2026-09-24 evening (modality surface + client-contract honesty)** —
  Outward still flat (Ollama v0.34.4; LiteLLM bar v1.102.1 / tip
  v1.104.0-dev.1 MCP sessions watch; Portkey rpw + Kong/vLLM unchanged).
  Morning non-chat governance filings left in flight. Next layer: missing
  image-generations route, Idempotency-Key gap on modality endpoints, silent
  facade drops of Ollama 0.34 knobs, `week`/`rpw` budget aliases, moderations/
  rerank integration pins. Filed five. Pruned shipped watch rows
  (migrate/skew, facade core options, thinking controls).

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
