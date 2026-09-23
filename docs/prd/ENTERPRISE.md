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

Second scan same day. Morning's client-parameter-fidelity set is still open
in the queue (non-stream tools, `service_tier` ingress, `strict`/`name`,
chat drop cluster, Anthropic thinking/metadata/`top_k`) plus two P3 audio
follow-ups. This run pivots to **facade + Responses shape + drop visibility**
— gaps the earlier pass left in the watch row.

**Outward (this run):** **LiteLLM v1.104.0-dev.1** still the tip (MCP live
sessions, Transcribe, A2A Entra); stable patch train unchanged from morning.
**Ollama v0.34.3**, **vLLM 0.30.0** unchanged. **OpenRouter** Batch API
(09-22) + US in-region routing (09-09) — daari already has Batch/Files;
region pin stays a watch until a tenant asks. **Kong AI Gateway** changelog
shows 2.0.3 (08-31), not a 2.1 GA bump. Portkey Agent Gateway / Prisma AIRS
narrative unchanged (compliance deferred).

**Inward theme: facade contract + Responses shapes (code-verified):**
`/api/show` advertises thinking controls but `OllamaChatRequest` never
declares top-level `think`/`format`/`keep_alive` (`extra="ignore"`);
generate has `format` only. Responses `from_responses_body` only renames
`max_output_tokens` — Agents SDK `reasoning.effort` and `text.format` never
reach `SamplingParams`. No default dropped-params header. MCP explorers get
`Method not found` on `resources/list` / `prompts/list`. Stream host failover
has unit tests but no hermetic TTFT ceiling.

Verified fine / already queued — not re-filing: chat param cluster and
Anthropic thinking budget (morning filings); Ollama show thinking object;
Idempotency-Key docs; pooled httpx/Postgres.

---

## Scored gap table

| # | Gap | Impact | Effort | Who does it best today | Why daari wins local-first | Action |
|---|-----|:--:|:--:|------------------------|----------------------------|--------|
| 1 | **Facade ignores chat `think`/`format`/`keep_alive`** — show advertises thinking; native Ollama clients' knobs vanish under `extra="ignore"` | 5 | 2 | Ollama native | Desktop IDEs get the full router only if the facade matches real Ollama | File ([#1011](https://github.com/naveenreddyalka/daari/issues/1011)) |
| 2 | **Responses-native shapes unmapped** — `reasoning.effort`, `text.format`, `tool_choice`, `service_tier` never feed `SamplingParams` (chat names only) | 4 | 2 | Direct OpenAI Responses / Agents SDK | Same local grammar + L6 path as chat when agents speak Responses | File ([#1012](https://github.com/naveenreddyalka/daari/issues/1012)) |
| 3 | **No default dropped-param visibility** — operators cannot see which knobs the tier ignored without opt-in | 4 | 2 | Portkey / LiteLLM dashboards | Localhost can put the drop list on the same response the agent already holds | File ([#1013](https://github.com/naveenreddyalka/daari/issues/1013)) |
| 4 | **MCP `resources/list` / `prompts/list` Method not found** — tools-only server; explorers still probe and paint red errors | 3 | 1 | LiteLLM MCP gateway | Honest empty lists keep local handshake green | File ([#1014](https://github.com/naveenreddyalka/daari/issues/1014)) |
| 5 | **No hermetic TTFT ceiling for stream host failover** — unit coverage only; regressions can hide in optional benches | 3 | 1 | (none — daari-specific) | Local-first streaming promise is enforceable only with a bound | File ([#1015](https://github.com/naveenreddyalka/daari/issues/1015)) |
| 6 | Morning parameter-fidelity queue (non-stream frontier tools, `service_tier` ingress, `strict`/`name`, chat drop cluster, Anthropic thinking/metadata/`top_k`) / OpenRouter in-region pin / MCP live-session visibility / moderations + rerank / WIF / A2A / SOC 2 / admin UI | 2–5 | 1–5 | LiteLLM / Portkey / cloud | Prior queue drains first; compliance waits for a paying ask | Watch / queued |

Pruned this run: none shipped since morning; Ollama thinking-controls watch
row stays resolved. Morning File rows remain open (not duplicated).

---

## Path to enterprise-grade — next 5 milestones

1. **Facade contract** — native Ollama `think`/`format`/`keep_alive` match
   what `/api/show` advertises so desktop clients stop lying to themselves.
2. **Lossless escalation** — drain the morning queue (non-stream tools,
   thinking budgets) so routing never changes request semantics.
3. **Responses shape fidelity** — Agents SDK `reasoning` / `text.format`
   map onto the same SamplingParams as chat.
4. **No silent drops** — default `X-Daari-Dropped-Params` (or equivalent)
   on every response that ignored a knob.
5. **MCP explorer hygiene** — empty resources/prompts lists; live-session
   visibility stays deferred until a fleet asks.

Compliance non-goals (WIF, A2A, SOC 2, admin UI, OCR until a paying ask) stay deferred.

---

## Changelog

- **2026-09-23 (facade + Responses shapes)** — Second scan. Outward flat
  vs morning (LiteLLM still on v1.104.0-dev.1; OpenRouter Batch 09-22 noted;
  Kong 2.0.3). Inward: facade drops `think`/`format`/`keep_alive`, Responses
  shape mapper gap, missing drop header, MCP probe 404s, no hermetic stream
  failover ceiling. Filed five. Morning fidelity filings remain open.

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
