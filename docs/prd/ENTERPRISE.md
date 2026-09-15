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

## Where daari stands (verified in-tree, 2026-09-15 late)

**Fleet-completeness sprint closed the same day it opened.** #481–#485 all
merged (PRs #490–#494): Postgres Responses, Redis session pins + cost rollup,
Postgres hash-chained audit, signed budget webhooks, W3C traceparent
propagation. Helm/doctor/bench hygiene (#476–#478) shipped earlier the same
day. The backlog drained to empty mid-session; this refill keeps the loop fed.

**Positioning:** LiteLLM’s stable line advanced again — **v1.100.0 (2026-09-06)**
adds access-group budgets, custom auto-router tiers, MCP token introspection,
and `GET /public/v1/model_hub`; v1.101’s routing offensive +
`/v1/responses/input_tokens` + OpenAI WIF remain the parity bar. daari’s
routing stays Apache 2.0 (LiteLLM meters `auto_router` behind enterprise).
Portkey / Kong / OpenRouter / Ollama / vLLM / MCP SEP-1933: no material
delta since the morning scan.

**Inward theme of this refill: finish the leftovers and raise the soft
edges.** Profile pins were skipped when session affinity moved to Redis;
doctor still doesn’t warn on sqlite audit under fleet signals or unsigned
webhooks; Responses grow without retention; request-count quotas hard-402
with no soft band; L0 cold misses stampede under concurrent identical keys.

---

## Scored gap table

| # | Gap | Impact | Effort | Who does it best today | Why daari wins local-first | Action |
|---|-----|:--:|:--:|------------------------|----------------------------|--------|
| 1 | **Profile pins still per-process** — #482 moved session pins to Redis; `ProfilePinStore` left behind | 3 | 2 | LiteLLM (central sessions) | Same Redis + fail-open pattern; agent tool loops skip re-classify across replicas | **Filed** (P2) |
| 2 | **Doctor blind to audit backend + unsigned webhooks** — #478 covered batches/files only | 3 | 1 | — | Warn only when fleet signals / webhook URL already set; SQLite stays fine for single-node | **Filed** (P2) |
| 3 | **Stored Responses never prune** — Files got retention (#456); Responses accumulate forever | 3 | 2 | LiteLLM (TTL everywhere) | Opt-in local retention; reuse existing sweep | **Filed** (P2) |
| 4 | **Request-count quotas have no soft warning/alert** — USD soft-band only; local $0 traffic cliffs at 402 | 3 | 2 | LiteLLM budgets | Soft signal keeps agents on L3–L5 before the hard stop | **Filed** (P2) |
| 5 | **L0 exact-cache stampede** — concurrent identical cold misses all hit upstream | 3 | 2 | GPTCache / LiteLLM singleflight | One in-flight fill + fan-out maximizes $0 hits under agent fan-out | **Filed** (P2) |
| 6 | **`/v1/responses/input_tokens`** — LiteLLM v1.101 stable | 2 | 2 | LiteLLM | Reuse local estimate / Anthropic count path | Watch (client ask) |
| 7 | **Percentile-TTFT routing** — LiteLLM still partly rc | 2 | 3 | LiteLLM | Need Prometheus TTFT histograms first | Watch |
| 8 | **WIF upstream provider auth** | 3 | 3 | Portkey | `secret://oauth` covers most | Watch |
| 9 | **MCP agent identity (SEP-1933)** | 3 | 3 | MCP Tier-1 SDKs | Draft | Watch |
| 10 | **SOC 2 / Gemini facade / A2A / admin UI / images / realtime** | 2–3 | 2–5 | Kong / LiteLLM | No new client demand | Watch / non-goal |

Pruned this run: #476–#485 rows (all shipped same day).

Open backlog after this run: five new P2 issues from the late-15 refill
(profile pins, doctor follow-on, Responses retention, request-quota soft
band, L0 singleflight).

---

## Path to enterprise-grade — next 5 milestones

1. **Close the Redis leftover** — profile pins must share the same fleet path as session pins.
2. **Honest fleet doctor** — audit backend + signed webhook checks so operators see config lies early.
3. **Bounded local artifact stores** — Responses retention parity with Files.
4. **Soft capacity signals** — request-quota warnings/alerts before the 402 cliff.
5. **Cache stampede resistance** — L0 singleflight under concurrent identical misses.

---

## Changelog

- **2026-09-15 (late)** — Same-day fleet sprint closed (#481–#485 → PRs
  #490–#494; #476–#478 earlier). Backlog empty mid-session; refilled five P2
  leftovers (profile pins, doctor audit/webhook warnings, Responses
  retention, request-quota soft band, L0 singleflight). Outward: LiteLLM
  v1.100.0 (access-group budgets, custom router tiers) noted; v1.101 bar
  unchanged. Portkey/Kong/OpenRouter/Ollama flat.
- **2026-09-15** — Fifth same-day drain: #463–#467 merged overnight (PRs
  #469–#473). Never-empty refill + scheduled Actions `prd-cycle` (PR #479)
  and session cost rollup (PR #480). Filed #481–#485 (fleet half-finished).
- **2026-09-14** — Redis resilience audit; filed #463–#467; all shipped
  overnight.
- **2026-09-13→08-28** (condensed) — tenancy, batches, Kong parity, labeler,
  Apache 2.0, this PRD.
