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

The 09-20 resilience/modality set drained overnight: local TTS
(`/v1/audio/speech` + guide + Helm), all-local-down frontier failover
(`local_pool.frontier_failover` + doctor + Helm), OTLP logs export, and
per-key admission priority all shipped; L1 embed-model cache versioning
([#845](https://github.com/naveenreddyalka/daari/issues/845)) and `models
warm` ([#843](https://github.com/naveenreddyalka/daari/issues/843)) remain
queued alongside Idempotency-Key and a P3 docs/test tail.

**Outward (this run):** flat. LiteLLM **v1.103.0-rc.1** is the only mover:
config-file ownership, Fuse/capability routing, gateway hardening (MCP client
allowlisting, live-session force-close, RFC 8693 token exchange, per-issuer
JWT scoping), **lifetime `total_spend` caps + temporary budget increases**
(gap filed below), TypeSafe Jev decision-model passthrough, and a VS Code
provider extension — still RC, bar stays v1.102.0. Portkey **v2.23.0**, Kong
**2.0.3**, Ollama **v0.34.2** (0.34.3 still rc), vLLM **0.29.0**, OpenRouter
(last change 08-19), and MCP SEP-1933 (still draft) all unchanged.

**Inward theme: the data plane was never hardened.** A security/client-compat
audit found `daari serve` has no TLS or mTLS path (`uvicorn.run` without
`ssl_*`, no reverse-proxy contract in SECURITY.md, no Helm cert values); no
request-body size cap (rate-limit middleware buffers `await request.body()`
unbounded — only the file store 413s); invalid-key 401s are audited (deduped
60s) but never throttled; and frontier escalation silently degrades agent
clients — the frontier stream relay yields only text deltas (tool-call deltas
dropped), `tool_choice` and Anthropic `output_format` are parsed but never
forwarded upstream. Verified fine, not filed: auth middleware open-path list
is tight (`/health`, `/ready`, `/metrics` only when keyless); `secret://`
refs + `redact_secrets` cover error/config echo paths; `config validate`
shipped; structured outputs reach local backends; local streams relay
tool-call deltas correctly.

---

## Scored gap table

| # | Gap | Impact | Effort | Who does it best today | Why daari wins local-first | Action |
|---|-----|:--:|:--:|------------------------|----------------------------|--------|
| 1 | **No TLS/mTLS on `daari serve`** — uvicorn launched without `ssl_keyfile`/`ssl_certfile`; no client-cert option; no documented reverse-proxy TLS contract; Helm has no cert values. Prompts and API keys transit plaintext | 5 | 2 | Kong (native termination); LiteLLM (`ssl_*` flags) | Single-box on-prem deployments have no ingress/mesh in front; a gateway holding hashed keys must speak HTTPS out of the box | File ([#932](https://github.com/naveenreddyalka/daari/issues/932)) |
| 2 | **No request-body size cap** — middleware buffers full body unbounded before any check; 100MB chat JSON = memory exhaustion on the same box running the models; only file uploads 413 | 4 | 2 | Kong (413 handling); nginx defaults | Gateway shares RAM with the local model runtime — early 413 protects the whole box | File ([#933](https://github.com/naveenreddyalka/daari/issues/933)) |
| 3 | **Frontier escalation drops tool fidelity** — frontier SSE relay strips `delta.tool_calls`; `tool_choice` and Anthropic `output_format` parsed but never forwarded; agent turns truncate whenever routing lands on L6 | 4 | 3 | LiteLLM (uniform passthrough) | Tier escalation is daari's core mechanic — L6 must be a lossless superset of local or agents can't trust the fallback | File ([#934](https://github.com/naveenreddyalka/daari/issues/934)) |
| 4 | **Invalid-key attempts unthrottled** — 401s audited (60s dedupe) but no failure counter/backoff/lockout; online key brute-force limited only by throughput | 3 | 2 | Cloud gateways (WAF in front) | Workstation/LAN deployments have no WAF; built-in throttling makes hashed keys a real defense | File ([#935](https://github.com/naveenreddyalka/daari/issues/935)) |
| 5 | **No lifetime spend caps or temporary budget boosts** — windows are day/month/Nh/Nd only; LiteLLM v1.103-rc ships lifetime `total_spend` + temp increases + team `model_max_budget` | 3 | 2 | LiteLLM v1.103-rc | Ledger already tracks all-time spend locally; contractor "$50 total, ever" keys and audited auto-expiring boosts are cheap sums, no cloud | File ([#936](https://github.com/naveenreddyalka/daari/issues/936)) |
| 6 | **CORS/security headers / `input_audio` chat blocks (local ASR inline) / `parallel_tool_calls`+`logit_bias`+`top_logprobs` passthrough / MCP session visibility / moderations + rerank / `daari migrate` + skew guard / OCR / Fuse routing / WIF / A2A / SOC 2 / admin UI** | 2–4 | 1–5 | LiteLLM / Kong / cloud | Browser hardening, chat-audio, and param passthrough wait for a client ask; rest deferred | Watch |

Pruned this run: the resilience/modality rows (frontier failover, TTS, OTLP
logs, admission priority) — shipped overnight; L1 embed versioning stays
queued as an issue, not a row.

---

## Path to enterprise-grade — next 5 milestones

1. **Encrypt the data plane** — native TLS/mTLS on serve, Helm cert wiring, documented reverse-proxy contract.
2. **Bound every request** — body-size 413 plus the existing deadline/disconnect/admission set makes resource abuse impossible by construction.
3. **Lossless escalation** — frontier legs preserve streamed tool calls, `tool_choice`, and structured output so agent clients never notice the tier.
4. **Auth that survives exposure** — brute-force throttling on 401s, completing the hashed-keys + audit story.
5. **Spend governance parity** — lifetime caps and audited temporary boosts on top of multi-window budgets.

Compliance non-goals (WIF, A2A, SOC 2, admin UI, OCR until a paying ask) stay deferred.

---

## Changelog

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
