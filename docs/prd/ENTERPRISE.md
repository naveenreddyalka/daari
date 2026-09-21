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

## Where daari stands (verified in-tree, 2026-09-21)

Morning's data-plane set (TLS/mTLS, body-size 413, frontier tool fidelity,
401 throttle, lifetime budgets) is queued and untouched this run. Still
queued from earlier: L1 embed-model cache versioning, `models warm`,
Idempotency-Key (in flight), Helm TTS base URL, virtual-key admission
priority CLI, plus a P3 docs/test tail.

**Outward (this run):** LiteLLM stable bar is **v1.102.0** (2026-09-19) —
auto-router controls, native OCR default, PgBouncer/spend-collector
reliability, MCP schema-discovery proxy, OTel HTTP/JSON export; **v1.103.0rc1**
exists on PyPI (lifetime caps already filed this morning — watch for stable).
Portkey enterprise line still **v2.23.x**-era (no fresh GA bump since last
scan). Kong AI Gateway **2.0** GA (MCP bundling, modality cost, identity
policies) unchanged. Ollama **v0.34.2** stable / **v0.34.3-rc1** still rc.
vLLM **0.29.0**, OpenRouter quiet since 08-19.

**Inward theme: browser clients and agent SDK knobs still go dark.**
`daari web-ui` is a separate origin hitting a key-gated API with no CORS and
no security headers; rate-limit middleware buffers every GET body; agent SDKs
send `parallel_tool_calls` / `logit_bias` / `top_logprobs` that
`extra="ignore"` silently drops; MCP tool counters exist in metrics but never
reach `/v1/daari/stats` or the web-ui; stores migrate on open with no
operator `migrate` / schema skew guard. Verified fine, not filed: morning
security findings remain accurate; local streams still relay tool-call
deltas; `config validate` and secret redaction unchanged.

---

## Scored gap table

| # | Gap | Impact | Effort | Who does it best today | Why daari wins local-first | Action |
|---|-----|:--:|:--:|------------------------|----------------------------|--------|
| 1 | **No CORS / security headers** — web-ui (11437) fetches key-gated API (11435) cross-origin; no `CORSMiddleware`, no `X-Content-Type-Options` / `X-Frame-Options` / `Referrer-Policy` | 4 | 2 | Kong / LiteLLM (native CORS + header baselines) | Laptop dashboards talk to `127.0.0.1` with no nginx — one knob unblocks ops UI | File ([#938](https://github.com/naveenreddyalka/daari/issues/938)) |
| 2 | **Rate-limit buffers every GET body** — middleware always `await request.body()` + JSON parse, including `/v1/models`, traces, report; distinct from any 413 size cap | 3 | 1 | Kong / nginx (header-only for safe methods) | Same box as Ollama — cheaper admission leaves RAM for local inference | File ([#939](https://github.com/naveenreddyalka/daari/issues/939)) |
| 3 | **Agent sampling knobs silently dropped** — `parallel_tool_calls`, `logit_bias`, `top_logprobs` absent from `ChatCompletionRequest` / `openai_payload()`; `extra="ignore"` → 200 with no effect | 3 | 2 | LiteLLM (uniform passthrough) | Local warns in meta; frontier/OpenAI-compat forward so L3–L6 feel identical to SDKs | File ([#940](https://github.com/naveenreddyalka/daari/issues/940)) |
| 4 | **MCP invisible on laptop stats** — `mcp_tool_calls` in metrics snapshot but omitted from `/v1/daari/stats`; no task list; web-ui has no MCP panel | 3 | 2 | Cloud gateways (MCP live in same console) | One `web-ui serve` shows deny/guardrail pressure without Grafana | File ([#941](https://github.com/naveenreddyalka/daari/issues/941)) |
| 5 | **No `daari migrate` / schema skew guard** — stores migrate quietly on open; policy sync has no schema version; upgrade guide admits the gap | 3 | 3 | LiteLLM / cloud (versioned config claims) | Offline dry-run + doctor warn before a laptop-fleet skew bricks policy | File ([#942](https://github.com/naveenreddyalka/daari/issues/942)) |
| 6 | **MCP session registry + force-close / MCP egress httpx reuse / doctor mcp_servers probe / `input_audio` chat blocks / moderations + rerank / OCR / Fuse / WIF / A2A / SOC 2 / admin UI** | 2–4 | 1–5 | LiteLLM / Kong / cloud | Session ops and chat-audio wait for a client ask; compliance deferred | Watch |

Pruned this run: morning data-plane rows stay queued as issues (not table
rows). L1 embed versioning / models warm / Idempotency-Key remain queued.

---

## Path to enterprise-grade — next 5 milestones

1. **Encrypt + bound the data plane** — TLS/mTLS, body-size 413, 401 throttle (queued from morning).
2. **Browser-safe ops surface** — CORS allowlist + default security headers so web-ui and IDE webviews work with keys.
3. **Lossless agent SDK parity** — frontier tool fidelity (queued) plus sampling/tool-parallel passthrough.
4. **MCP visible without Grafana** — stats + web-ui surface tool/task pressure; session registry later.
5. **Upgrade without fear** — `daari migrate --dry-run` and policy schema skew guards for laptop fleets.

Compliance non-goals (WIF, A2A, SOC 2, admin UI, OCR until a paying ask) stay deferred.

---

## Changelog

- **2026-09-21 (browser/ops + agent SDK knobs)** — Second run today. Outward:
  LiteLLM **v1.102.0** stable (auto-router, native OCR, gateway reliability);
  **v1.103.0rc1** on PyPI (lifetime caps already queued). Portkey/Kong/Ollama/
  vLLM flat vs morning. Inward (code-verified): no CORS/security headers,
  rate-limit buffers GETs, three sampling fields silently dropped, MCP stats
  missing from `/v1/daari/stats`+web-ui, no migrate/skew CLI. Filing five.
  Morning data-plane five remain queued.

- **2026-09-21 (data-plane hardening + lossless escalation)** — Yesterday's
  five-row table drained overnight except L1 embed versioning and models
  warm. Outward flat; only LiteLLM v1.103.0-rc.1 moved (config ownership,
  Fuse routing, gateway hardening, lifetime caps — parity row filed; VS Code
  provider extension noted). Inward security/client-compat audit
  (code-verified): no TLS/mTLS, no body cap, no 401 throttle, frontier strips
  tool-call deltas / `tool_choice` / `output_format`, no lifetime budgets.
  Verified fine: tight open-path list, secret redaction, config validate,
  local-stream tool deltas. Filing five.

- **2026-09-20 (two runs)** — Governance secondary ingress (MCP route meta,
  batch limiter bypass, embed L0 scope, Helm auth knobs, model warm) then a
  resilience/modality delta (L1 embed versioning, all-local-down failover,
  TTS, admission priority, OTLP logs). Outward: LiteLLM v1.102.0 on PyPI;
  v1.103.0-rc.1 watch; Ollama 0.34.2 stable.

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
