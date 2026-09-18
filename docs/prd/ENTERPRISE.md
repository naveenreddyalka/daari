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

## Where daari stands (verified in-tree, 2026-09-18 evening)

Fleet/HA, tenancy, and observability themes are fully drained: Postgres backends
for keys/teams/audit/responses/batches/files/ledger, Redis fail-open, distributed
session pins, signed webhooks, traceparent propagation, team RPM/TPM,
request-count quotas, region pinning, keys export/import, graceful Helm rollout,
RFC 7662 introspect, stats `backend_summary`, and the whole soft-budget /
Grafana / metrics pass all shipped. The backlog degraded into P3 docs/test
trivia over the last two days — this run re-seeds it with governance and
cost-accounting surfaces that were never built.

**Positioning:** LiteLLM v1.101.0 remains the outward bar (model access groups,
`/spend/logs` export, auto-router — the latter enterprise-gated). Portkey
v2.23.0 (09-18: ElevenLabs speech endpoints, streaming usage default,
`providerSlug` metrics label) is provider-breadth, not gateway-core. Kong quiet
at 2.0.3 (08-31); OpenRouter changelog unmoved since 08-19; Ollama v0.34.2
stable (desktop-only changes); vLLM 0.29.0.

**Inward theme:** model *governance* and *chargeback* are the two enterprise
controls daari still lacks — a virtual key can call any model its tier cap
allows, and spend is only day-aggregated, so per-request showback is impossible.

---

## Scored gap table

| # | Gap | Impact | Effort | Who does it best today | Why daari wins local-first | Action |
|---|-----|:--:|:--:|------------------------|----------------------------|--------|
| 1 | **Per-key/team model allowlists + access groups** — keys carry only `tier_cap`; no way to restrict a key to named models/groups ([LiteLLM model access groups](https://docs.litellm.ai/docs/proxy/users), [OpenRouter BYOK `allowed_models`](https://openrouter.ai/docs/changelog)) | 5 | 2 | LiteLLM | Enforcement at the same edge that owns local tiers; Apache 2.0 core vs. enterprise-gated governance | File P1 |
| 2 | **Per-request spend rows + chargeback export** — ledger is day-aggregated (`daari/observability/usage.py`); no CSV/JSONL row export for showback ([LiteLLM /spend/logs](https://docs.litellm.ai/docs/proxy/cost_tracking)) | 4 | 3 | LiteLLM | Only daari can show the $0-local vs. frontier split per request — the core savings story, unprovable today | File P2 |
| 3 | **`daari config validate` + strict nested keys** — unknown *nested* config keys are silently ignored (typo'd `budgets:` block no-ops); upgrade guide admits no validate command | 3 | 2 | Kong (decK validate) | Single-binary self-host means daari.yaml *is* the control plane; a silent typo is a silent policy hole | File P2 |
| 4 | **Master key rotation with overlap** — `server.api_key` is one string; virtual keys rotate with 24h grace but the master key needs restart + hard cutover | 3 | 2 | Cloud gateways (managed) | Zero-downtime credential ops without a control plane is exactly the self-host pitch | File P2 |
| 5 | **Per-provider/per-tier retry + timeout policy** — only global `upstream.retry` and a local/frontier timeout split; no per-provider overrides in the failover chain | 3 | 2 | LiteLLM router settings | Local tiers and frontier providers have wildly different latency envelopes; one knob can't fit both | File P2 |
| 6 | Access-group budgets / multiproc metrics / MCP introspect depth | 3 | 3–4 | LiteLLM | Baselines landed; deepen on local demand | Watch |
| 7 | Audio/speech endpoints (`/v1/audio/*`) — Portkey v2.23 ships ElevenLabs natively | 2 | 3 | Portkey | Non-goal until a daari-served client sends audio | Watch |
| 8 | WIF / A2A / SOC 2 / admin UI | 2–3 | 3–5 | Kong / cloud | No new client demand | Watch / non-goal |

---

## Path to enterprise-grade — next 5 milestones

1. **Model governance** — per-key/team model allowlists and named access groups,
   enforced on every gateway surface (chat, responses, embeddings, facade).
2. **Chargeback-grade accounting** — per-request spend rows with bounded
   retention and CSV/JSONL export; the local-savings story becomes auditable.
3. **Config lifecycle** — `daari config validate`, strict nested-key rejection,
   documented upgrade path from N-1.
4. **Zero-downtime credential ops** — master key rotation with overlap window,
   mirroring the virtual-key grace pattern.
5. **Route policy depth** — per-provider/per-tier retry and timeout overrides in
   the failover chain.

---

## Changelog

- **2026-09-18 (evening)** — All 19 fleet/tenancy/resilience issues from the
  09-14→09-16 runs confirmed shipped; backlog had degraded to P3 docs/test
  trivia. Rebuilt table around governance + chargeback: filing five issues
  (model allowlists P1; spend export, config validate, master key rotation,
  per-provider retry/timeout P2). Outward: Portkey v2.23.0 (ElevenLabs,
  streaming-usage default — daari already honors `include_usage`), Ollama
  v0.34.2 stable (desktop-only), LiteLLM stable bar unchanged at v1.101.0,
  Kong/OpenRouter/vLLM flat. New watch row: audio endpoints.
- **2026-09-18 (early)** — Soft-budget / observability drain: pruned shipped gap
  rows 1–8 from the 2026-09-17 night table and follow-ons. Watch rows only
  remained; milestones retargeted to larger enterprise surfaces.
- **2026-09-17 (4 runs)** — Morning→night refills drained same-day: ops/RBAC,
  facade/bench, stats/web-ui, scrape port, Anthropic SSE L0, Grafana alert + MCP
  panels, Helm `metrics_port`, `agent_turn` meta, soft USD warn path, team
  gauges, introspect, hermetic 402. Outward flat all day (LiteLLM v1.101.0 bar).
- **2026-09-16 (3 runs)** — Fleet-auth theme: Postgres keys/teams, Helm graceful
  rollout, team RPM/TPM, keys export/import, facade capabilities; plus dry-run,
  TTFT counter, bench + harness rows. Ollama v0.34.1 stable.
- **2026-09-15 and earlier** — Condensed: loop restructure (never-empty refill +
  14:00 UTC Actions prd run), fleet story (responses/pins/audit/webhooks/
  traceparent), resilience + metering (Redis fail-open, audit coverage,
  cross-replica batches/files, region pinning, request quotas), stored-artifact
  tenancy, Batch/Files API, pricing refresh, session affinity, stall escalation,
  MCP pagination, Apache 2.0 relicense, this PRD's creation (2026-08-28).
