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

## Where daari stands (verified in-tree, 2026-09-23)

Full drain again: both 09-22 sets (correlation + data-plane/stream-fidelity)
merged, plus overnight extras — Idempotency-Key, CORS/security headers,
TLS/body-cap/auth-throttle docs, `input_audio` on chat and Responses, MCP
`ttlMs`/`cacheScope`, ASR/TTS/embed retry, X-Request-ID on every surface and
hop, pooled httpx and Postgres. Queue at scan start: two P3 audio follow-ups.

**Outward (this run):** **Ollama v0.34.3 stable** — `/api/show` thinking
controls (`values`+`default`); daari's facade parity already shipped, watch
row resolved. **LiteLLM v1.102.1** patch wave (backports); dev channel
v1.104.0-dev.1 shows MCP live-session visibility, Amazon Transcribe
passthrough, A2A Foundry Entra auth, per-deployment `max_parallel_requests`
429. **Portkey v2.24.0**, **Kong 2.1.0**, **vLLM 0.30.0**, OpenRouter
(08-19), MCP blog (08-22 roadmap) all unchanged.

**Inward theme: client parameter fidelity** (code-verified): frontier OpenAI
non-stream `execute()` never attaches `tools` (stream path does);
`service_tier` is plumbed through `SamplingParams` but neither HTTP ingress
model declares it; the `response_format` rebuild hardcodes `name:"daari"` and
strips `strict`; `store`/`metadata`/`prediction`/`modalities`/output
`audio`/`verbosity`/`web_search_options` die on `extra="ignore"` and parsed
`logprobs`/`n` never reach `openai_payload()`; Anthropic request-level
`thinking` budgets and `metadata` are dropped and `top_k` misses
`to_anthropic_payload`. Verified fine — not filing: `parallel_tool_calls`/
`logit_bias`/`top_logprobs` forwarded; `max_completion_tokens` precedence;
`reasoning_effort` → Ollama `think`; Anthropic system blocks +
`cache_control` + `output_format` + thinking-block replay; facade
`/api/show` thinking + `/api/tags` capabilities.

---

## Scored gap table

| # | Gap | Impact | Effort | Who does it best today | Why daari wins local-first | Action |
|---|-----|:--:|:--:|------------------------|----------------------------|--------|
| 1 | **Non-stream frontier OpenAI omits `tools`/`tool_choice`** — stream path attaches them, `execute()` does not; agent loops break exactly on escalation | 5 | 1 | Everyone (table stakes) | Lossless escalation is the pitch — same behavior local and frontier | File ([#1006](https://github.com/naveenreddyalka/daari/issues/1006)) |
| 2 | **`service_tier` dropped at both HTTP ingresses** — `SamplingParams` forwards it but the request models never deliver it | 4 | 1 | Portkey v2.22+ (tier-aware pricing incl. `fast`) | Feeds daari's own admission priority + budget pricing | File ([#1005](https://github.com/naveenreddyalka/daari/issues/1005)) |
| 3 | **`json_schema` `strict` + `name` stripped in `response_format` rebuild** — structured-output contract silently downgraded on frontier + openai-kind local | 4 | 1 | LiteLLM / direct APIs | vLLM/llama.cpp honor `strict` grammar decoding — local tiers deserve the real contract | File ([#1008](https://github.com/naveenreddyalka/daari/issues/1008)) |
| 4 | **OpenAI chat silent-drop cluster** — `store`, `metadata`, `prediction`, `modalities`, output `audio`, `verbosity`, `web_search_options` eaten by `extra="ignore"`; `logprobs`/`n` parsed but never forwarded; warnings need opt-in header | 4 | 2 | LiteLLM / Portkey (full passthrough) | Drop-in replacement means every knob works or warns loudly | File ([#1007](https://github.com/naveenreddyalka/daari/issues/1007)) |
| 5 | **Anthropic `thinking` budget / `metadata` / `top_k` parity** — Claude Code's request-level thinking never reaches L6; budget could map to local `think` | 4 | 2 | Direct Anthropic API | Only a router can map a thinking budget onto local reasoning levels | File ([#1009](https://github.com/naveenreddyalka/daari/issues/1009)) |
| 6 | Ollama facade `keep_alive`/`format`/`think` passthrough (facade advertises thinking controls but ignores chat `think`) / MCP live-session visibility (LiteLLM dev) / moderations + rerank / WIF / A2A / SOC 2 / admin UI | 2–3 | 2–5 | Ollama native / LiteLLM / cloud | Facade + session gaps file on client demand; compliance waits for a paying ask | Watch |

Pruned this run: both 09-22 sets and the 09-21 security/browser rows (shipped);
Ollama thinking-controls watch row (parity verified in-tree).

---

## Path to enterprise-grade — next 5 milestones

1. **Lossless escalation** — tools on non-stream frontier calls and thinking
   budgets forwarded; routing must never change request semantics.
2. **Parameter fidelity** — `service_tier`, `strict` structured outputs, and
   the passthrough cluster so evals through daari match direct calls.
3. **No silent drops** — a visible warning channel for anything the serving
   tier can't honor, without opt-in headers.
4. **Facade completeness** — Ollama facade honors `keep_alive`/`format`/
   `think` so native clients get what `/api/show` advertises.
5. **MCP session visibility** — stateless ingress today; LiteLLM's dev
   channel ships live-session views, file when a fleet asks.

Compliance non-goals (WIF, A2A, SOC 2, admin UI, OCR until a paying ask) stay deferred.

---

## Changelog

- **2026-09-23 (client parameter fidelity)** — Ollama v0.34.3 stable
  (thinking controls; facade parity already in-tree), LiteLLM v1.102.1
  backport wave + v1.104.0-dev.1 (MCP live sessions, Transcribe, A2A Entra),
  rest unchanged. Inward audit found silent drops across both ingresses:
  non-stream frontier tools bug, `service_tier` never delivered, `strict`
  stripped, seven-param drop cluster, Anthropic thinking/metadata/top_k.
  Filed five. Both 09-22 sets fully drained overnight.

- **2026-09-22 (two runs)** — Data-plane efficiency + stream truncation
  fidelity (pooled httpx, whole-stream keepalive, `stream_incomplete` +
  breaker, stream host failover, Postgres pool), then correlation + modality
  resilience (X-Request-ID forward/echo everywhere, MCP cache hints, ASR/TTS/
  embed retry, `input_audio`). Portkey v2.24.0, Kong 2.1.0, vLLM 0.30.0.

- **2026-09-21 (two runs)** — Data-plane hardening + lossless escalation
  (TLS/mTLS, body cap, 401 throttle, frontier tool parity, lifetime budgets),
  then browser/ops + agent SDK knobs (CORS/security headers, safe-method
  rate-limit skip, sampling passthrough, MCP stats, migrate/skew CLI).

- **2026-09-20 (two runs)** — Governance secondary ingress (MCP route meta,
  batch limiter bypass, embed L0 scope, Helm auth knobs, model warm) then a
  resilience/modality delta (L1 embed versioning, all-local-down failover,
  TTS, admission priority, OTLP logs). Ollama 0.34.2 stable.

- **2026-09-19 (four runs)** — Embed/ASR measurement, cache tenancy +
  request lifecycle (tenant cache_scope, disconnect cancel, invalidation,
  deadline, request-log retention), embedding chargeback, day-cap surfaces.

- **2026-09-18 (three runs)** — Soft-budget/observability drain; governance +
  chargeback theme (model allowlists, spend export, config validate, master
  key rotation, per-provider retry/timeout); Responses lifecycle, idempotency,
  audio route, request-rate HPA, rpd. Portkey v2.23.0.

- **2026-09-15 → 09-17 and earlier** — Condensed: loop restructure
  (never-empty refill + scheduled Actions prd run), fleet-auth theme, fleet
  story, resilience + metering, stored-artifact tenancy, Batch/Files API,
  pricing refresh, session affinity, stall escalation, MCP pagination,
  Apache 2.0 relicense, this PRD's creation (2026-08-28).
