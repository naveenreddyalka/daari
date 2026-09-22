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

The 09-21 sets drained almost entirely overnight: TLS/mTLS, body-size 413,
lifetime budgets, CORS + security headers, safe-method rate-limit skip,
sampling-knob passthrough, MCP stats, migrate dry-run + skew guard all merged;
frontier tool parity and the 401 throttle are in open PRs. Today's autodev
refill (X-Request-ID echo, doctor MCP probe, MCP egress client reuse) shipped
within 30 minutes of filing. Remaining queue: admission-priority CLI, L1 embed
versioning, Idempotency-Key (in flight), plus a P3 docs/test tail.

**Outward (this run):** three competitors moved **today**. **Portkey v2.24.0**
(09-22): per-attempt retry logging, **truncated-stream detection on all
providers** (in-band `stream_incomplete` event, partial kept in log, excluded
from cache), MCP OAuth robustness. **Kong AI Gateway 2.1.0** (09-22): MCP
protocol revision 2026-07-28 up/downstream with `ttlMs`/`cacheScope` cache
hints and version negotiation, W3C trace context on MCP tool calls,
per-modality token costs, CEL ACL expressions. **vLLM v0.30.0** stable
(09-22): engine internals (Fast Start weight cache, watermarking) — nothing
daari must speak natively. LiteLLM bar still **v1.102.0** (v1.103.0-rc.1),
Ollama **v0.34.2** / 0.34.3 still rc, OpenRouter quiet since 08-19.

**Inward theme: data-plane efficiency + stream truncation fidelity**
(code-verified): every upstream hop except MCP egress builds a fresh
`httpx.AsyncClient` per request (Ollama, OpenAI-compat, MLX, frontier,
embeddings, TTS, ASR — zero `httpx.Limits`/keepalive anywhere); SSE
keepalives stop after the first chunk so mid-stream thinking pauses get
idle-killed by proxies; a frontier stream dying after deltas ends with **no
in-band signal** (local tiers do signal); stream failures never feed the
per-host circuit breaker and streams pick one host with no pre-first-token
failover (non-stream loops hosts); Postgres stores `psycopg.connect` per
operation. Verified fine, not filed: retries are per-attempt-traced with
metrics (Portkey retry-logging parity already covered); partial streams are
never cached; request deadline, traceparent, OTLP logs all shipped;
speech/ASR meter spend; MCP ingress negotiates 2026-07-28.

---

## Scored gap table

| # | Gap | Impact | Effort | Who does it best today | Why daari wins local-first | Action |
|---|-----|:--:|:--:|------------------------|----------------------------|--------|
| 1 | **Per-request `httpx.AsyncClient` on every hop** — Ollama/OpenAI-compat/MLX/frontier/embeds/TTS/ASR make a TCP(+TLS) handshake per call; only MCP egress pools | 5 | 2 | LiteLLM / Portkey (pooled provider clients, single-digit-ms overhead claims) | Gateway shares the box with Ollama — pooled keepalive turns handshake tax into local latency headroom | File ([#971](https://github.com/naveenreddyalka/daari/issues/971)) |
| 2 | **SSE keepalive dies after first chunk** — `stream_with_keepalive` heartbeats only pre-first-token; 30–120s thinking pauses get idle-killed by nginx/LBs | 4 | 2 | Portkey / Kong (whole-stream heartbeats) | Local tiers pause too (model load, CPU laptops) — survives stock reverse proxies with zero tuning | File ([#972](https://github.com/naveenreddyalka/daari/issues/972)) |
| 3 | **Silent frontier stream truncation** — death after deltas ends the stream with no in-band event; stream failures never hit `breaker.record_failure()` | 4 | 2 | Portkey v2.24.0 (`stream_incomplete` event, log retention, cache exclusion) | Laptops die mid-stream more than clouds — honest truncation + breaker feedback is fleet trust | File ([#973](https://github.com/naveenreddyalka/daari/issues/973)) |
| 4 | **No stream host failover** — streaming `pick()`s one host; a dead host fails the tier though siblings are healthy; non-stream loops hosts | 4 | 3 | LiteLLM (router retries pre-stream) | Pre-first-token failover is lossless; agent/IDE traffic is ~all streamed | File ([#974](https://github.com/naveenreddyalka/daari/issues/974)) |
| 5 | **Postgres connect-per-operation** — ledger/batches/files/responses open `psycopg.connect(dsn)` each op; no pool, operators need external PgBouncer | 4 | 2 | LiteLLM (PgBouncer reliability work in latest stables) | In-process `psycopg[pool]` removes a whole moving part at daari fleet scale | File ([#975](https://github.com/naveenreddyalka/daari/issues/975)) |
| 6 | **X-Request-ID not forwarded upstream / MCP `ttlMs`+`cacheScope` cache hints (Kong 2.1.0) / ASR-TTS-embed retry wrapper / moderations + rerank / `input_audio` blocks / WIF / A2A / SOC 2 / admin UI** | 2–3 | 1–5 | Kong / LiteLLM / cloud | Correlation + cache hints are small parity deltas; compliance waits for a paying ask | Watch |

Pruned this run: all five 09-21 browser/ops rows (shipped overnight).

---

## Path to enterprise-grade — next 5 milestones

1. **Pooled data plane** — shared upstream HTTP clients and Postgres pools; the
   gateway overhead story becomes measurable, not apologized for.
2. **Streams that never lie** — whole-stream keepalive, in-band truncation
   events, breaker feedback, pre-first-token host failover.
3. **Lossless agent SDK parity** — frontier tool fidelity + 401 throttle land
   (open PRs), Idempotency-Key completes.
4. **Fleet QoS** — admission-priority CLI ships; per-key priority becomes
   usable end to end.
5. **Correlation everywhere** — X-Request-ID forwarded upstream, MCP cache
   hints, so one request is one thread through logs, traces, and MCP calls.

Compliance non-goals (WIF, A2A, SOC 2, admin UI, OCR until a paying ask) stay deferred.

---

## Changelog

- **2026-09-22 (data-plane efficiency + stream truncation fidelity)** — Three
  same-day competitor releases: **Portkey v2.24.0** (truncated-stream
  detection, per-attempt retry logs), **Kong 2.1.0** (MCP 2026-07-28 + cache
  hints, modality costs), **vLLM 0.30.0** (internals only). LiteLLM bar
  v1.102.0 unchanged. Inward (code-verified): per-request httpx clients on
  every non-MCP hop, first-chunk-only SSE keepalive, silent frontier stream
  truncation with no breaker feedback, no stream host failover, Postgres
  connect-per-op. Verified fine: retry tracing, partial-stream cache
  exclusion, deadline/traceparent/OTLP, MCP 2026-07-28 negotiation. Filing
  five. The 09-21 sets drained overnight; today's autodev refill shipped in
  30 minutes.

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
