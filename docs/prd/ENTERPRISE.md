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

## Where daari stands (verified in-tree, 2026-10-14)

**Loop velocity.** The whole 10-13 morning + eve tables drained in <24h yet
again: rows 85–89 and 92–95 (decisions catalog discovery, per-MCP-server
rpm/tpm, PrometheusRule alert pack, Postgres request/event log backend,
/mcp/proxy + tasks Prom parity, Grafana dashboard ConfigMap, image.digest
pin, scoped in-flight panels, cache-invalidate counters) all shipped via
PRs #1642–#1650. Open: member budget webhooks (90), DEC/SYS bench docs (91),
LiteLLM-GA compare row (96), docs pins 72–74/78, and `agent:working` rows
62–63/65–67.

**Outward.** LiteLLM v1.105.1 stable patch (10-14) + 1.106.0-rc.2; a noisy
1.107.0-dev.1 carries watchables (Errors/failed-request observability tab,
M365 + GitHub Copilot OAuth providers, detect-only guardrails streamed
live, more /v1/decisions providers). **Headline: OpenAI announced the GPT-4
series API shutdown on 10-14** (gpt-4o/4o-mini/4.1/4.1-mini removed
2027-01-14 → gpt-6-luna) and a programmatic `shutdown_date` field on
`GET /v1/models`. Portkey 2.28.0, Kong 2.2.0, vLLM 0.31.0, OpenRouter
(Oct 9), MCP blog (Aug 22) flat; Ollama 0.40.4 stable is runtime-only
(decision models in CLI, MLX Kev). Anthropic Dynamic Workflows beta stays a
platform-side non-goal.

**Inward theme: parity depth on the overnight wave.** Code audit verified:
`daari erase` never touches the new Postgres request-log table (JSONL-only
erase path); Postgres outage semantics are inconsistent (VK store can go
*open* after a boot-time connect failure, budgets fail open on silent 0.0
spend, `/ready` never probes PG); per-server MCP 429s send Retry-After but
write no audit row and no Prom reject; `daari migrate` inspects SQLite
stores only; `models.lifecycle` ships empty defaults, so doctor/410 gates
never fire on OpenAI's own retirement calendar.

---

## Scored gap table

| # | Gap | Impact | Effort | Who does it best today | Why daari wins local-first | Action |
|---|-----|:--:|:--:|------------------------|----------------------------|--------|
| 97 | Subject erasure for the Postgres request/event log backend | 5 | 2 | — (LiteLLM DB logs have no erase verb) | Air-gapped GDPR erase in one CLI run | Filed [#1651](https://github.com/naveenreddyalka/daari/issues/1651) |
| 98 | Fail-closed auth + signalled budget degrade on PG outage; `/ready`+doctor PG probes; documented matrix | 5 | 4 | — (LiteLLM proxy-DB behavior opaque) | Explicit per-store fail-open/closed beats silent open | Filed [#1652](https://github.com/naveenreddyalka/daari/issues/1652) |
| 99 | Ship default model lifecycle (OpenAI 10-23 + 2027-01-14 waves) + `shutdown_date` on /v1/models | 4 | 2 | LiteLLM cost-map `deprecation_date` strings | Doctor + fail-closed 410 light up on install | Filed [#1653](https://github.com/naveenreddyalka/daari/issues/1653) |
| 100 | Audit + Prom reject parity for per-server MCP rpm/tpm 429s | 4 | 2 | Portkey cloud analytics | Greppable on-box proof a ceiling fired | Filed [#1654](https://github.com/naveenreddyalka/daari/issues/1654) |
| 101 | `daari migrate` + doctor visibility for Postgres store schemas | 4 | 3 | LiteLLM boot-time Alembic | Dry-run SQLite **and** PG before a rolling upgrade | Filed [#1655](https://github.com/naveenreddyalka/daari/issues/1655) |
| 90 | Per-member budget threshold webhooks on shared team keys | 3 | 3 | LiteLLM 1.105 member alerts | Catch a runaway agent via the on-box ledger | Open [#1633] |
| 91 | BENCHMARKS.md DEC/SYS cross-link + decisions L0 cache-hit scenario | 3 | 1 | — (benchmarking honesty) | Publish the on-box warm-judgment win | Open [#1634] |
| 96 | compare-litellm: 1.105.0 GA framing + `litellm.agent()`/Lens vs on-box multi_agent | 2 | 1 | LiteLLM release notes | Honest local-first positioning | Open [#1640] |
| 72 | `daari stats --help` mentions `virtual_keys` | 2 | 1 | — (CLI honesty) | Same JSON operators already dump | Open |
| 73 | compare-litellm: LiteLLM 1.105 RC Decisions vs daari | 2 | 1 | LiteLLM release notes | On-box Decisions already ship | Open |
| 74 | Hermetic pin: virtual-keys.md documents `/v1/models` allowlist | 2 | 1 | — (docs regression) | Keep ACL sentence in CI | Open |
| 78 | compare-litellm: LiteLLM 1.106 decision-model guardrail watch | 2 | 1 | LiteLLM release notes | Honest local-first positioning | Open |
| 62 | End-user inventory + per-user block/cap overrides | 5 | 3 | OpenRouter end-users / LiteLLM | Ledger already knows every user | Open |
| 63 | Named guardrail profiles bindable per key/team | 5 | 3 | OpenRouter guardrail assign / Portkey | Per-tenant policy, zero hops | Open |
| 65 | Web-ui: honor keys/teams `has_more` + render `report.users` | 4 | 2 | LiteLLM admin UI | Same-box console finishes the job | Open |
| 66 | Bound/paginate report `clients`/`users` rollups | 4 | 2 | LiteLLM paged usage | Fleet-safe JSON on-box | Open |
| 67 | multi_agent nested usage: per-subagent `model` for cost-true pricing | 4 | 2 | OpenAI / LiteLLM FinOps | Ledger already meters nested tokens | Open |
| 6 | Hot-reload `config.yaml` | 3 | 2 | LiteLLM config ownership | Open — needs long session | Open |
| 7 | Per-key tool-name allowlist for Messages `mcp_servers` | 4 | 3 | LiteLLM `mcp_tool_permissions` | Parked (needs ≥60m session) | Parked |
| 87 | Shipped PrometheusRule alert pack: breaker/budget/5xx/queue/guardrails/key-expiry | 5 | 2 | LiteLLM alerting docs / Kong | Batteries-included day-2 ops on-box | Shipped |
| 88 | Fleet-durable request/event log backend (postgres) — was last per-pod store | 5 | 4 | LiteLLM DB spend logs | Air-gapped fleets need on-box durability | Shipped |
| 89 | /mcp/proxy + MCP tasks Prom parity; `mcp` modality registered | 4 | 2 | Kong MCP analytics / LiteLLM | One governed MCP door must be observable | Shipped |
| 85 | Advertise local decisions catalog on `/v1/models` + Ollama `/api/tags` | 3 | 2 | LiteLLM 1.106 decisions UI | BYOK clients discover on-box judges | Shipped |
| 86 | Per-server rpm/tpm ceilings on `integrations.mcp_servers` | 4 | 2 | LiteLLM MCP limits | Protect small MCP backends from one tenant | Shipped |
| 92–95 | Eve packaging set: Grafana ConfigMap; image.digest pin; scoped in-flight panels; cache-invalidate counters | 3–4 | 1–2 | Kong / LiteLLM charts | One `helm install` lights on-box panels | Shipped |
| 24 | Grafana panel for `compact_to_fit_applied` | 2 | 1 | LiteLLM spend dashboards | Shipped | Shipped |
| 25 | Dedicated stats/Prom counter for MCP grant fail-closed | 3 | 1 | LiteLLM MCP 403 metrics | Shipped | Shipped |
| 26 | Refuse MCP `initialize` when key has no grant | 4 | 1 | LiteLLM initialize 403 | Shipped | Shipped |
| 27 | Stats for estimated tokens dropped by compact-to-fit | 3 | 2 | LiteLLM compact telemetry | Shipped | Shipped |
| 28 | Refresh compare-litellm for LiteLLM 1.104 GA | 2 | 1 | LiteLLM release notes | Shipped | Shipped |
| 19 | Config ownership for `routing.compact_to_fit.*` | 3 | 2 | LiteLLM config ownership | Shipped | Shipped |
| 20 | Doctor tip when compact_to_fit is enabled | 2 | 1 | — (ops honesty) | Shipped | Shipped |
| 21 | Hermetic pin: compact_to_fit in config + routing-tiers | 2 | 1 | — (docs regression) | Shipped | Shipped |
| 22 | `daari_meta` + stats when compact_to_fit actually trims | 3 | 2 | LiteLLM compact telemetry | Shipped | Shipped |
| 23 | Opt-in fail-closed MCP when key has no MCP grant | 4 | 2 | LiteLLM `require_key_mcp_access_defined` | Shipped | Shipped |
| 8 | Full DCR; A2A; Realtime/WS; stdio MCP; M365 catalog; Skills; FIPS; HIPAA BAA | 2–4 | 3–5 | Portkey / Kong / LiteLLM / OpenAI | Demand-triggered | Watch |

Shipped this week (do not re-file): PrometheusRule alert pack; Postgres
request/event log backend; /mcp/proxy + tasks Prom parity + `mcp` modality;
per-server MCP rpm/tpm ceilings (Retry-After headers); decisions catalog on
discovery facades; Helm Grafana ConfigMap + image.digest pin; scoped
in-flight panels; cache-invalidate Prom counters; decision-guardrail async
data plane; teams metadata Postgres/export parity; concurrency caps across
CLI/admin/web-ui/Helm/Prom; hermetic RPM clock; audit reject rows.

Watch rows (do not file yet): cache-invalidate enterprise audit row +
stats/web-ui/Grafana/alert surface (Prom-only today — fold into next admin
audit slice); alert-pack + dashboard coverage for the new mcp_egress /
cache-invalidate series (file on operator ask); Anthropic-shaped /v1/models
cards drop the `decision` capability tag local decisions carry on
OpenAI/Ollama facades (fold into next catalog sweep); MCP server ceilings
absent from config-editor PATCH subset + Helm values (file on fleet ask);
LiteLLM 1.107-dev watchables at GA (failed-request Errors tab, M365/GitHub
Copilot OAuth providers, detect-only guardrails streamed live vs daari's
buffering scanner, hosted_vllm + Databricks decisions providers); SCIM +
multi-issuer/audience SSO (regulated-buyer ask); `gen_ai.agent.*` semconv;
per-user request-count RPD; Prometheus exemplars; decisions catalog
pricing for drex/microsoft ids ($0 local by design); gpt-6-luna Decisions
schema drift; OpenRouter BYOK `declared_region` / IP allowlists; Anthropic
Managed Agents Dynamic Workflows + Compliance API (non-goal); Kong 2.2 MCP
bundling + modality cost (buyer ask); Portkey JWT JIT (operator ask);
OpenAI in-product HIPAA BAA (compliance non-goal).

Verified fine this run — don't re-audit: request-log PG backup catalog
(`pg_dump --table=daari_request_log`) + retention prune on PG + Helm
forced-backend env + doctor fleet-backend tip; PrometheusRule expressions
all reference real series/labels (no phantoms); MCP server 429 Retry-After +
X-RateLimit-Scope headers + doctor ceilings tip; decisions advertised on
OpenAI /v1/models + Ollama /api/tags + /api/show with `decision` capability;
cache-invalidate Prom counters + entries-removed series; scoped in-flight
Grafana panels; Redis rate-limit outage contract (sqlite_fallback/fail_open
+ /ready redis check + degraded gauge) — the gap is the **Postgres** side.

---

## Path to enterprise-grade — next 5 milestones

1. **Compliance closes the loop** — subject erasure on the PG request-log
   (row 97), the last store `daari erase` misses.
2. **Honest failure semantics** — fail-closed auth + signalled budget
   degrade + `/ready`/doctor PG probes + documented matrix (row 98).
3. **Lifecycle out of the box** — shipped OpenAI retirement calendar +
   `shutdown_date` parity so doctor/410 gates fire on install (row 99).
4. **Provable governance** — audit + Prom parity for per-server MCP 429s
   (row 100), member budget webhooks (row 90).
5. **Fleet upgrade confidence** — migrate/doctor PG schema visibility
   (row 101), then the admin-plane rows (62–67) as sessions free up.

Compliance non-goals (SCIM, WIF depth, A2A, SOC 2 program, Realtime/WS,
FIPS builds, HIPAA BAA) stay deferred until buyer demand.

---

## Changelog

- **2026-10-14 (overnight-wave parity depth)** — Marked rows 85–89 + 92–95
  Shipped (PRs #1642–#1650 drained both 10-13 tables in <24h). Drained the
  dead 10-13 eve sibling PRD PR to main (pin-test failure; its rows adopted
  here). Filed rows 97–101: PG request-log erasure, PG outage fail-closed
  semantics + probes, shipped model lifecycle + `shutdown_date` parity
  (OpenAI announced the GPT-4 API shutdown 10-14), MCP per-server 429
  audit/Prom parity, migrate/doctor PG schema visibility. Outward: LiteLLM
  1.105.1 stable patch; OpenAI GPT-4 retirement wave; all other bars flat.

- **2026-10-13 (day-2 operations depth)** — Filed rows 87–91: PrometheusRule
  alert pack, fleet-durable request/event log backend, /mcp/proxy + tasks
  Prom parity, per-member budget webhooks, BENCHMARKS DEC/SYS cross-link.
  Adopted eve-sibling rows 85–86.

- **2026-10-13 eve (day-2 observability packaging)** — Sibling scan filed
  rows 92–96 (Grafana ConfigMap, image.digest pin, scoped in-flight panels,
  cache-invalidate counters, LiteLLM GA compare); its PRD PR failed the pin
  test and was drained to main 10-14.

- **2026-10-12 → 08-28** — Condensed: concurrency + decision-guardrail
  depth; control-plane honesty + MCP server rpm; export honesty + doctor
  ACL; team DR + console lifecycle; RBAC floors + decisions agility;
  key/end-user lifecycle; admin-plane honesty; Decisions/OAuth/multi-agent;
  governance parity; LiteLLM 1.104; Apache 2.0; this PRD's creation.
