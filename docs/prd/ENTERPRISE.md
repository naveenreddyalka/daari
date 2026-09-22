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

## Where daari stands (verified in-tree, 2026-09-22)

Second scan same day. Morning set (pooled httpx, whole-stream SSE keepalive,
`stream_incomplete` + breaker, stream host failover, Postgres pool) is open in
the `auto-dev` queue; X-Request-ID echo on chat, doctor MCP probe, and MCP
egress client reuse already merged. Remaining older queue: admission-priority
CLI, L1 embed versioning, Idempotency-Key, frontier tool parity / 401 throttle
(open PRs), plus a P3 docs/test tail.

**Outward (this run):** no newer competitor cuts since the morning scan —
**Portkey v2.24.0** (truncated-stream detection, per-attempt retry logs),
**Kong AI Gateway 2.1.0** (MCP 2026-07-28 `ttlMs`/`cacheScope`, W3C on MCP
tool calls, modality costs, CEL ACL), **vLLM 0.30.0** (engine internals).
LiteLLM bar still **v1.102.0**; Ollama **v0.34.2**; OpenRouter quiet.

**Inward theme: end-to-end correlation + modality resilience** (code-verified):
`X-Request-ID` resolves+echoes on chat only — never forwarded on
`inject_trace_headers()` upstream hops, and Anthropic / Responses / Ollama /
embeddings / audio omit the response header; MCP `tools/list` negotiates
2026-07-28 but emits no `_meta` cache hints (Kong 2.1.0 parity); ASR / TTS /
embed HTTP skip `RetryPolicy`/`run_upstream` (chat path already has it);
`content.py` extracts images but drops OpenAI `input_audio` blocks. Verified
fine / already filed: pooled clients + stream fidelity (morning set); partial
streams uncached; deadline/traceparent/OTLP; MCP 2026-07-28 negotiation;
speech/ASR meter spend.

---

## Scored gap table

| # | Gap | Impact | Effort | Who does it best today | Why daari wins local-first | Action |
|---|-----|:--:|:--:|------------------------|----------------------------|--------|
| 1 | **`X-Request-ID` not forwarded upstream** — hops only get W3C `traceparent`; Ollama/frontier/ASR/TTS/embed/MCP never see the gateway id | 4 | 1 | Kong / Portkey (end-to-end correlation) | One box → one id through local + frontier logs without APM | File ([#977](https://github.com/naveenreddyalka/daari/issues/977)) |
| 2 | **`X-Request-ID` echo missing on non-chat surfaces** — Anthropic, Responses, Ollama facade, embeddings, audio omit the response header | 3 | 1 | Portkey (all unified routes) | Cursor / Claude Code / JetBrains / ASR clients join spend rows to client traces | File ([#978](https://github.com/naveenreddyalka/daari/issues/978)) |
| 3 | **MCP `tools/list` lacks `ttlMs`/`cacheScope`** — 2026-07-28 negotiated, result is bare `{"tools":…}`; Kong 2.1.0 emits cache hints | 3 | 2 | Kong AI Gateway 2.1.0 | Local catalogs change rarely — honest TTL cuts agent re-list churn | File ([#979](https://github.com/naveenreddyalka/daari/issues/979)) |
| 4 | **ASR / TTS / embed skip gateway retry** — bare httpx; chat already uses `RetryPolicy`/`run_upstream` | 4 | 2 | LiteLLM / Portkey (uniform modality retry) | Local whisper/TTS/Ollama embed flaps should not 502 the IDE | File ([#980](https://github.com/naveenreddyalka/daari/issues/980)) |
| 5 | **`input_audio` content blocks dropped** — `content.py` handles images only; voice-agent chat loses audio on local tiers | 3 | 2 | LiteLLM / cloud gateways | Optional local ASR inject keeps voice turns on-box | File ([#981](https://github.com/naveenreddyalka/daari/issues/981)) |
| 6 | **Pooled httpx / whole-stream keepalive / `stream_incomplete`+breaker / stream host failover / Postgres pool** (morning set) / moderations+rerank / WIF / A2A / SOC 2 / admin UI | 2–5 | 1–5 | LiteLLM / Portkey / Kong / cloud | Data-plane set already queued; compliance waits for a paying ask | Watch / in flight |

Pruned this run: morning data-plane rows move to watch/in-flight; 09-21 browser/ops rows stay shipped.

---

## Path to enterprise-grade — next 5 milestones

1. **Correlation everywhere** — forward + echo `X-Request-ID` on every surface and
   upstream hop so one request is one thread through logs and spend.
2. **Pooled data plane** — shared upstream HTTP clients and Postgres pools
   (morning backlog) make gateway overhead measurable.
3. **Streams that never lie** — whole-stream keepalive, in-band truncation,
   breaker feedback, pre-first-token host failover (morning backlog).
4. **MCP catalog honesty** — `ttlMs`/`cacheScope` hints so agents cache
   `tools/list` instead of re-listing every turn.
5. **Modality parity** — ASR/TTS/embed retry + `input_audio` passthrough so
   voice and embed paths match chat resilience.

Compliance non-goals (WIF, A2A, SOC 2, admin UI, OCR until a paying ask) stay deferred.

---

## Changelog

- **2026-09-22b (correlation + modality resilience)** — No newer competitor
  cuts since morning. Inward (code-verified): `X-Request-ID` chat-only echo
  and never forwarded upstream; non-chat gateways omit response header; MCP
  `tools/list` missing `ttlMs`/`cacheScope` despite 2026-07-28; ASR/TTS/embed
  skip `RetryPolicy`; `input_audio` blocks dropped. Filing five. Morning
  data-plane set remains open in the queue.

- **2026-09-22 (data-plane efficiency + stream truncation fidelity)** — Three
  same-day competitor releases: **Portkey v2.24.0** (truncated-stream
  detection, per-attempt retry logs), **Kong 2.1.0** (MCP 2026-07-28 + cache
  hints, modality costs), **vLLM 0.30.0** (internals only). LiteLLM bar
  v1.102.0 unchanged. Inward: per-request httpx clients, first-chunk-only SSE
  keepalive, silent frontier stream truncation, no stream host failover,
  Postgres connect-per-op. Filed five (pooled httpx → Postgres pool).

- **2026-09-21 (two runs)** — Data-plane hardening + lossless escalation
  (TLS/mTLS, body cap, 401 throttle, frontier tool parity, lifetime budgets),
  then browser/ops + agent SDK knobs (CORS/security headers, safe-method
  rate-limit skip, sampling passthrough, MCP stats, migrate/skew CLI).
  LiteLLM v1.102.0 stable; v1.103.0-rc.1 lifetime caps queued.

- **2026-09-20 (two runs)** — Governance secondary ingress (MCP route meta,
  batch limiter bypass, embed L0 scope, Helm auth knobs, model warm) then a
  resilience/modality delta (L1 embed versioning, all-local-down failover,
  TTS, admission priority, OTLP logs). Ollama 0.34.2 stable.

- **2026-09-19 (four runs)** — Embed/ASR measurement, cache tenancy +
  request lifecycle (tenant cache_scope, disconnect cancel, invalidation,
  deadline, request-log retention), embedding chargeback, day-cap surfaces.
  Ollama v0.34.3-rc1 thinking controls watch row added.

- **2026-09-18 (three runs)** — Soft-budget/observability drain; governance +
  chargeback theme (model allowlists, spend export, config validate, master
  key rotation, per-provider retry/timeout); Responses lifecycle, idempotency,
  audio route, request-rate HPA, rpd. Portkey v2.23.0.

- **2026-09-17 (4 runs)** — Ops/RBAC, facade/bench, stats/web-ui, scrape port,
  Anthropic SSE L0, Grafana alert + MCP panels, Helm metrics port, agent_turn
  meta, soft USD warn, team gauges, introspect, hermetic 402.

- **2026-09-16 (3 runs)** — Fleet-auth theme: Postgres keys/teams, Helm graceful
  rollout, team RPM/TPM, keys export/import, facade capabilities; plus dry-run,
  TTFT counter, bench + harness rows. Ollama v0.34.1 stable.

- **2026-09-15 and earlier** — Condensed: loop restructure (never-empty refill +
  scheduled Actions prd run), fleet story, resilience + metering, stored-artifact
  tenancy, Batch/Files API, pricing refresh, session affinity, stall escalation,
  MCP pagination, Apache 2.0 relicense, this PRD's creation (2026-08-28).
