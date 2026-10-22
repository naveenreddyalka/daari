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

## Where daari stands (verified in-tree, 2026-10-22 pm)

**Loop velocity.** Morning wave filed invoice/stream, enforcement poll,
service-tier degrade, fleet breaker Redis, and sampling-strip telemetry; those
issues remain open. Tenancy/console set (end-user inventory, guardrails, paged
reports) still `agent:working`.

**Outward.** Competitive landscape flat vs morning: LiteLLM still on the
1.107.0 compromise floor (**1.106.2** clean; Decisions/`hosted_vllm` and
OpenRouter `usage.cost` billing stay watchables until a verified non-compromised
GA). Anthropic org webhooks for enforcement are documented
(`user_profile.enforcement_action_*`, beta `webhooks-2026-10-07`) — push path
complements profile polling. OpenAI background Responses + `response.completed`
webhooks remain the cancel/notify bar. vLLM 0.32.0 security wave still has no
local-tier doc floor. Portkey/Kong flat for this cut.

**Inward theme: close the console and day-2 gaps left on the watch list.**
HTTP spend export already accepts `team`/`until`, but the web-ui omits them;
breaker status renders with no reset button. Grafana ships gzip Prom series
with zero panels and no TTL cache-write spend chart. Responses store can be
Postgres-shared, yet `_BACKGROUND_JOBS` cancel is still per-pod. vLLM guide
has no ≥0.32.0 security floor. Enforcement visibility needs webhook ingest,
not only poll.

---

## Scored gap table

| # | Gap | Impact | Effort | Who does it best today | Why daari wins local-first | Action |
|---|-----|:--:|:--:|------------------------|----------------------------|--------|
| 188 | Web-ui: spend-export `team`/`until` + systemone breaker reset | 4 | 2 | LiteLLM admin UI | Same-box FinOps + ops; HTTP already gated | Filed [#1871](https://github.com/naveenreddyalka/daari/issues/1871) |
| 189 | Grafana panels for gzip + cache-write TTL premium | 3 | 1 | LiteLLM spend dashboards | Bundled board shows invoice-true write premium | Filed [#1872](https://github.com/naveenreddyalka/daari/issues/1872) |
| 190 | Docs: vLLM security floor ≥0.32.0 in local-tier guide | 3 | 1 | Cloud “supported runtime” notes | Honest GPU floor next to pool config | Filed [#1873](https://github.com/naveenreddyalka/daari/issues/1873) |
| 191 | Fleet-coordinate Responses background job cancel | 4 | 3 | OpenAI background cancel | Redis/lease cancel stops the owning pod | Filed [#1874](https://github.com/naveenreddyalka/daari/issues/1874) |
| 192 | Ingest Anthropic org enforcement webhooks | 4 | 3 | Anthropic Admin API / SaaS gateways | Push joins local tenant map + audit | Filed [#1875](https://github.com/naveenreddyalka/daari/issues/1875) |
| 183–187 | Morning 10-22: streamed cache-write billing; enforcement poll; service-tier degrade; fleet breaker Redis; sampling-strip soft_warning/Prom | 3–4 | 1–3 | OpenAI / Anthropic / Kong | Invoice, blast-radius, HA truths | Open |
| 171–182 | 10-20/10-21 waves: breaker truth; TTL cache billing; user profiles; invalidate tenancy; facade `show`; console export; `between_tools` + gzip telemetry; Flint; LiteLLM compromise advisory; version-safe sampling | 2–5 | 1–3 | LiteLLM / Ollama / Anthropic | Billing truth, tenancy, catalog honesty | Shipped |
| 136–170 | 10-18 → 10-20 waves: `resultType`; fast-mode; `:cloud` fences; systemone; speed-keyed caches; spend slices; `schema_ok`; events windows | 2–5 | 1–3 | LiteLLM / Portkey / Kong / vLLM | Protocol, egress, FinOps, judge ops | Shipped |
| 62 | End-user inventory + per-user block/cap overrides | 5 | 3 | OpenRouter / LiteLLM | Ledger already knows every user | Open |
| 63 | Named guardrail profiles bindable per key/team | 5 | 3 | OpenRouter / Portkey | Per-tenant policy, zero hops | Open |
| 65 | Web-ui: honor keys/teams `has_more` + render `report.users` | 4 | 2 | LiteLLM admin UI | Same-box console finishes the job | Open |
| 66 | Bound/paginate report `clients`/`users` rollups | 4 | 2 | LiteLLM paged usage | Fleet-safe JSON on-box | Open |
| 67 | multi_agent nested usage: per-subagent `model` | 4 | 2 | OpenAI / LiteLLM FinOps | Ledger already meters nested tokens | Open |
| 6 | Hot-reload `config.yaml` | 3 | 2 | LiteLLM config ownership | Open — needs long session | Open |
| 7 | Per-key tool-name allowlist for Messages `mcp_servers` | 4 | 3 | LiteLLM `mcp_tool_permissions` | Parked (≥60m session) | Parked |
| 8 | Full DCR; A2A; Realtime/WS; stdio MCP; M365; Skills; FIPS; HIPAA BAA | 2–4 | 3–5 | Portkey / Kong / LiteLLM | Demand-triggered | Watch |

Watch rows (do not file yet): OpenAI `response.completed` webhooks for
background Responses (after row 191 cancel lands); `migrate --downgrade`;
per-user RPD; SCIM + multi-issuer SSO; Portkey WIF for upstream creds (buyer
ask); LiteLLM post-quarantine clean 1.107 rebuild watchables
(ID-JAG/OAuth-delegate, `agent_access_default_deny`, OpenRouter `usage.cost`)
once a verified non-compromised GA exists; Ollama Flint GPU beyond Mac;
systemone multi-upstream; Prometheus exemplars + `gen_ai.agent.*`; Kong
Skills/passthrough demand.

Verified fine this run — don't re-audit: spend-export HTTP already filters
`team`/`until`/`model`/`usage_speed` (gap is console wiring only); breaker
reset authz tested; gzip Prom series exist (gap is Grafana + cache-write TTL
series/panel); facade think/format; Helm digest pin + cosign docs; catalog
version-safe after sampling strip.

---

## Path to enterprise-grade — next 5 milestones

1. **Console finishes HTTP truths** — spend-export team/until + breaker reset
   on the same-box UI (row 188).
2. **Day-2 boards for new meters** — gzip + cache-write TTL premium on the
   bundled Grafana board (row 189), with the vLLM security floor documented
   (row 190).
3. **Fleet-true background cancel** — stop Responses workers on the owning
   pod from any replica (row 191).
4. **Push blast-radius** — Anthropic org enforcement webhooks into local
   tenant map (row 192), alongside morning enforcement poll.
5. **Drain morning + tenancy waves** — streamed cache-write billing, tier
   degrade, shared breaker, sampling telemetry; end-user inventory and
   guardrail profiles still in flight (rows 62–67, 183–187).

Compliance non-goals (SCIM, WIF depth, A2A, SOC 2 program, Realtime/WS,
FIPS builds, HIPAA BAA) stay deferred until buyer demand.

---

## Changelog

- **2026-10-22 pm (console + day-2 packaging)** — Outward flat vs morning;
  Anthropic org enforcement webhooks documented as push complement; vLLM
  0.32.0 security floor still undocumented. Filed rows 188–192: web-ui
  spend/breaker controls, Grafana gzip + cache-write TTL, vLLM floor docs,
  Responses background cancel coordination, Anthropic webhook ingest.
  Pruned watch items that became filings.

- **2026-10-22 (finish the truths the wave started)** — Marked rows 171–182
  Shipped. Outward: LiteLLM compromise post-mortem; Anthropic user-profile
  `enforcement_status`; OpenAI service-tier restrictions; Ollama 0.40.8 GA;
  vLLM 0.32.0 security wave. Filed rows 183–187.

- **2026-10-21 + pm (breaker truth, invoice-true cache billing, user
  profiles; LiteLLM compromise + Anthropic API-version footgun)** — Filed
  rows 173–182; marked 161–172 Shipped/Superseded.

- **2026-10-20 (finish the knobs + evening speed-keyed ops)** — Filed rows
  163–172. Outward: LiteLLM 1.106.0 GA; Anthropic
  `thinking.types.between_tools`.

- **2026-10-19 → 08-28** — Condensed: decisions-upstream depth; fast-mode
  cache truth; `resultType`/egress/billing waves; lifecycle/tenancy/DR;
  LiteLLM 1.104–1.106; Apache 2.0; this PRD's creation.
