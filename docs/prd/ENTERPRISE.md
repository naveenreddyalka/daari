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

## Where daari stands (verified in-tree, 2026-09-15)

**Fifth consecutive same-day drain — and the loop now feeds itself.** The 09-14
refill #463–#467 all merged overnight (PRs #469–#473): Redis fail-open
resilience, audit coverage, cross-replica batches/files via Postgres, L6 region
pinning, and request-count quotas. Then, minutes before this run, a sibling
session landed the loop's biggest structural change: **never-empty refill**
(#474 → PR #479: a scheduled `prd-cycle` GitHub Actions workflow at 14:00 UTC,
plus autodev refilling 3–5 issues itself instead of idling on an empty backlog)
and the **session cost-avoided rollup** (#475 → PR #480). Three P2 issues from
that session were open at run start.

**Positioning:** the one outward event is **LiteLLM v1.101.0 going stable
2026-09-15** — the "routing offensive" (heuristic_v2, hybrid routing, MCP
semantic tool search, off-peak pricing, per-worker admission control) is no
longer rc-gated, and stable also adds `/v1/responses/input_tokens` token
counting and OpenAI workload-identity federation. daari already shipped parity
where it mattered (tool search, admission cap, stall escalation, session
affinity) and its routing stays Apache 2.0 while LiteLLM meters `auto_router`
behind an enterprise license. Everything else is flat: Portkey v2.22.0,
Kong 2.0.3 (08-31), OpenRouter changelog unmoved since 08-19, Ollama 0.34.0
(0.34.1-rc2 is app/MLX-only), vLLM 0.29.0, MCP spec 2026-07-28 with SEP-1933
still draft.

**Inward theme of this run: the fleet story is half-finished.** Batches, files,
and the ledger got shared backends, but at the Helm chart's own
`replicaCount: 2`: stored Responses (`store: true`, `previous_response_id`,
background polling) 404 on the replica that didn't serve the request; session
pins and the brand-new session cost rollup live in a per-process dict, so
fleet totals diverge; and the hash-chained audit log is per-pod SQLite, so any
one pod's `daari audit export` misses roughly half the fleet's events. Also
verified: budget webhooks are unsigned (spoofable, unverifiable), and OTel
spans neither honor inbound `traceparent` nor inject it upstream — one request
appears as three disconnected traces.

---

## Scored gap table

| # | Gap | Impact | Effort | Who does it best today | Why daari wins local-first | Action |
|---|-----|:--:|:--:|------------------------|----------------------------|--------|
| 1 | **Stored Responses break across replicas** — `response_store.py` is SQLite-only; batches/files got Postgres, responses missed | 4 | 2 | LiteLLM (DB-backed everywhere) | Keep zero-dep SQLite for single-node; one setting flips fleets to the Postgres the chart already ships | **Filed [#481](https://github.com/naveenreddyalka/daari/issues/481)** (P2) |
| 2 | **Session pins + cost rollup are per-process** — affinity misses behind round-robin; per-replica savings totals diverge | 3 | 2 | LiteLLM (central DB sessions) | Reuse the Redis the fleet already runs for cache/rate limits; fail open like the Redis-resilience work | **Filed [#482](https://github.com/naveenreddyalka/daari/issues/482)** (P2) |
| 3 | **Audit trail is per-pod** — hash chain + export only see local SQLite; fleet export is incomplete for SOC 2 | 4 | 3 | LiteLLM/Portkey (plain DB trails) | Nobody else has offline-verifiable chaining; make it fleet-complete and it stays a differentiator | **Filed [#483](https://github.com/naveenreddyalka/daari/issues/483)** (P2) |
| 4 | **Budget webhooks unsigned** — receivers can't authenticate; alerts spoofable into paging pipelines | 2 | 1 | Stripe-style HMAC is industry norm | `X-Daari-Signature` convention + `secret://` refs already in-tree; pure stdlib | **Done [#484](https://github.com/naveenreddyalka/daari/issues/484)** |
| 5 | **No W3C trace-context propagation** — inbound `traceparent` ignored, upstream calls uninstrumented; 3 disconnected traces per request | 3 | 2 | Kong OTel plugin / LiteLLM proxy | The routing ladder (cache hit, tier escalation) becomes visible inside the caller's own Jaeger/Tempo trace | **Done [#485](https://github.com/naveenreddyalka/daari/issues/485)** |
| 6 | **Helm/doctor/bench hygiene** — stale chart tag, SQLite-at-replicas warnings, hermetic perf suite | 2–3 | 2 | — | Filed by the 09-15 sibling session | Open: [#476](https://github.com/naveenreddyalka/daari/issues/476)–[#478](https://github.com/naveenreddyalka/daari/issues/478) (P2) |
| 7 | **Percentile-TTFT routing** — still rc-only (LiteLLM v1.102.0-rc.1) | 2 | 3 | LiteLLM `-rc` | Need latency histograms first | Watch (stable or operator SLO ask) |
| 8 | **`/v1/responses/input_tokens` counting** — LiteLLM v1.101 stable | 2 | 2 | LiteLLM | Anthropic `count_tokens` shipped; OpenAI-side estimate exists internally | Watch (client ask) |
| 9 | **WIF upstream provider auth** — now in Portkey v2.20, Kong 2.0.3, LiteLLM v1.101 stable | 3 | 3 | Portkey | `secret://oauth` covers most; WIF is keyless step further | Watch (operator demand for keyless creds) |
| 10 | **MCP agent identity** — SEP-1933 still draft; spec 2026-07-28 current | 3 | 3 | MCP Tier-1 SDKs | `secret://oauth` ready | Watch (SEP merge or fleet ask) |
| 11 | **SOC 2 / Gemini facade / A2A / admin UI / off-peak / `/v1/images` / realtime / streamed `usage.cost`** | 2–3 | 2–5 | Kong / LiteLLM | No new client demand | Watch / non-goal |

Pruned this run: #463–#467 rows (all shipped overnight, PRs #469–#473);
session-savings watch row (shipped as PR #480).

Open backlog after this run:
[#476](https://github.com/naveenreddyalka/daari/issues/476)–[#478](https://github.com/naveenreddyalka/daari/issues/478),
[#481](https://github.com/naveenreddyalka/daari/issues/481)–[#485](https://github.com/naveenreddyalka/daari/issues/485)
(all P2).

---

## Path to enterprise-grade — next 5 milestones

1. **Finish the fleet** ([#481](https://github.com/naveenreddyalka/daari/issues/481), [#482](https://github.com/naveenreddyalka/daari/issues/482)) — every stateful surface must be true at the chart's default replica count; stored Responses and session state are the two still lying.
2. **Fleet-complete compliance** ([#483](https://github.com/naveenreddyalka/daari/issues/483)) — the hash-chained audit log is a genuine differentiator only if one export covers the whole fleet.
3. **Trustworthy signals out** ([#484](https://github.com/naveenreddyalka/daari/issues/484)) — signed webhooks close the day-one security-review finding on the alerting path.
4. **One trace end-to-end** ([#485](https://github.com/naveenreddyalka/daari/issues/485)) — propagated trace context puts daari's routing ladder inside the observability stack enterprises already run.
5. **Honest defaults** ([#476](https://github.com/naveenreddyalka/daari/issues/476)–[#478](https://github.com/naveenreddyalka/daari/issues/478)) — chart, doctor, and benchmarks that tell operators the truth about what a config actually does.

---

## Changelog

- **2026-09-15** — Fifth same-day drain: #463–#467 merged overnight (PRs
  #469–#473). Loop structure changed minutes before this run: never-empty
  refill + scheduled Actions `prd-cycle` at 14:00 UTC (PR #479) and session
  cost rollup (PR #480) landed; sibling session filed #474–#478. **Two PRD
  cycles now exist (Actions 14:00 UTC, Cursor Automation 17:00 UTC) — later
  run each day must delta-scan.** Outward: LiteLLM v1.101.0 STABLE (routing
  offensive + `/v1/responses/input_tokens` + OpenAI WIF); Portkey v2.22.0,
  Kong 2.0.3, OpenRouter (08-19), Ollama 0.34.0, vLLM 0.29.0, SEP-1933 draft —
  all unchanged. Inward: fleet story half-finished — per-pod Responses store,
  per-process session pins/rollup, per-pod audit chain, unsigned budget
  webhooks, no trace-context propagation. Filed
  [#481](https://github.com/naveenreddyalka/daari/issues/481)–[#485](https://github.com/naveenreddyalka/daari/issues/485)
  (all P2).
- **2026-09-14** — Redis resilience audit: rate-limit middleware 500s on Redis
  outage, audit coverage holes, per-pod batches/files at default Helm
  replicas, no request-count quotas, no L6 region pin. Filed #463–#467; all
  shipped overnight.
- **2026-09-13** — Stored-artifact tenancy audit + Portkey v2.22 parity +
  files retention. Filed #452–#456; all shipped same day. Fixed a CI date
  bomb in the audit-export test.
- **2026-09-12** — Batch slice audit (governance bypass, `/v1/files`,
  durability, idle-yield) + `daari configure`. Filed #441–#445; all shipped
  same day.
- **2026-09-11 / 10** — Filed #418–#422, #430–#434 (Kong parity + Batch API),
  #409–#412; `AUTODEV_GH_TOKEN` set.
- **2026-09-09→08-28** (condensed) — #374–#401 refills, park era, labeler,
  Apache 2.0, this PRD.
