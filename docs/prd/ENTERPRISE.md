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

## Where daari stands (verified in-tree, 2026-10-14 eve)

**Loop velocity.** Morning PRD (#1656) filed compliance/ops rows 97–101; those
stay open. Overnight wave (PRs #1642–#1650) still the last feature merge set.
`agent:working` continues on admin-plane rows 62–63/65–67 + hot-reload / MCP
tool allowlist / local E2E regression.

**Outward.** LiteLLM **v1.107.0-dev.1** cut today (17:02 UTC): failed-request
tracking by HTTP status + caller, Admin UI Errors tab, M365 Copilot + GitHub
Copilot OAuth providers, detect-only guardrails streamed live when buffering
is off, `hosted_vllm` + Databricks `ai_decide` Decisions providers, Azure
Microsoft-Decision-1. Stable bar still 1.105.1; 1.106 remains rc.2. Ollama
0.40.4, vLLM 0.31.0, Portkey, Kong, OpenRouter unchanged since morning.
OpenAI GPT-4 series API shutdown (2027-01-14 → gpt-6-luna) + `shutdown_date`
on `/v1/models` still the lifecycle headline; Oct-23 wave is nine days out.

**Inward theme: admin-surface + day-2 packaging depth.** Code audit verified:
cache invalidate has Prom + `log_gateway_event` but **no** enterprise audit
row (unlike MCP activity abort); Anthropic-shaped `/v1/models` rebuilds
`capabilities` via `anthropic_capabilities()` and drops the `decision` tag
OpenAI/Ollama facades carry; `integrations.mcp_servers` rpm/tpm absent from
config-editor ownership and Helm values; Grafana/PrometheusRule ignore the
new `daari_cache_invalidate_*` series; `daari_errors_total` is an unlabeled
scalar while LiteLLM 1.107-dev ships status/caller Errors breakdowns.

---

## Scored gap table

| # | Gap | Impact | Effort | Who does it best today | Why daari wins local-first | Action |
|---|-----|:--:|:--:|------------------------|----------------------------|--------|
| 102 | Enterprise audit row for admin cache invalidate | 4 | 2 | LiteLLM / Portkey admin audit | Greppable on-box proof a purge fired | Filed [#1657](https://github.com/naveenreddyalka/daari/issues/1657) |
| 103 | Carry `decision` capability on Anthropic-shaped `/v1/models` cards | 3 | 1 | LiteLLM Decisions UI | Same catalog truth on every facade | Filed [#1658](https://github.com/naveenreddyalka/daari/issues/1658) |
| 104 | `mcp_servers` rpm/tpm in config-editor ownership + Helm values | 4 | 2 | LiteLLM MCP rate-limit UI | Fleet ceilings without hand-editing every pod | Filed [#1659](https://github.com/naveenreddyalka/daari/issues/1659) |
| 105 | Grafana panels + PrometheusRule for `cache_invalidate` series | 3 | 2 | Kong / LiteLLM charts | One helm install lights purge ops | Filed [#1660](https://github.com/naveenreddyalka/daari/issues/1660) |
| 106 | Label `daari_errors_total` by HTTP status + Errors breakdown (stats/web-ui) | 4 | 3 | LiteLLM 1.107-dev Errors tab | On-box failure forensics, no SaaS tab | Filed [#1661](https://github.com/naveenreddyalka/daari/issues/1661) |
| 97 | Subject erasure for the Postgres request/event log backend | 5 | 2 | — (LiteLLM DB logs have no erase verb) | Air-gapped GDPR erase in one CLI run | Open [#1651] |
| 98 | Fail-closed auth + signalled budget degrade on PG outage; `/ready`+doctor PG probes | 5 | 4 | — (LiteLLM proxy-DB behavior opaque) | Explicit per-store fail-open/closed | Open [#1652] |
| 99 | Ship default model lifecycle (OpenAI waves) + `shutdown_date` on /v1/models | 4 | 2 | LiteLLM cost-map `deprecation_date` | Doctor + fail-closed 410 on install | Open [#1653] |
| 100 | Audit + Prom reject parity for per-server MCP rpm/tpm 429s | 4 | 2 | Portkey cloud analytics | Greppable proof a ceiling fired | Open [#1654] |
| 101 | `daari migrate` + doctor visibility for Postgres store schemas | 4 | 3 | LiteLLM boot-time Alembic | Dry-run SQLite **and** PG | Open [#1655] |
| 90 | Per-member budget threshold webhooks on shared team keys | 3 | 3 | LiteLLM 1.105 member alerts | Catch a runaway agent on-box | Open [#1633] |
| 91 | BENCHMARKS.md DEC/SYS cross-link + decisions L0 cache-hit scenario | 3 | 1 | — (benchmarking honesty) | Publish the on-box warm-judgment win | Open [#1634] |
| 96 | compare-litellm: 1.105.0 GA framing + `litellm.agent()`/Lens vs multi_agent | 2 | 1 | LiteLLM release notes | Honest local-first positioning | Open [#1640] |
| 72–74/78 | Docs pins: stats help, compare RC/1.106, virtual-keys hermetic | 2 | 1 | — | CLI/docs honesty | Open |
| 62 | End-user inventory + per-user block/cap overrides | 5 | 3 | OpenRouter end-users / LiteLLM | Ledger already knows every user | Open |
| 63 | Named guardrail profiles bindable per key/team | 5 | 3 | OpenRouter / Portkey | Per-tenant policy, zero hops | Open |
| 65 | Web-ui: honor keys/teams `has_more` + render `report.users` | 4 | 2 | LiteLLM admin UI | Same-box console finishes the job | Open |
| 66 | Bound/paginate report `clients`/`users` rollups | 4 | 2 | LiteLLM paged usage | Fleet-safe JSON on-box | Open |
| 67 | multi_agent nested usage: per-subagent `model` for cost-true pricing | 4 | 2 | OpenAI / LiteLLM FinOps | Ledger already meters nested tokens | Open |
| 6 | Hot-reload `config.yaml` | 3 | 2 | LiteLLM config ownership | Open — needs long session | Open |
| 7 | Per-key tool-name allowlist for Messages `mcp_servers` | 4 | 3 | LiteLLM `mcp_tool_permissions` | Parked (needs ≥60m session) | Parked |
| 85–89 / 92–95 | Overnight wave: alert pack, PG request-log, MCP Prom/rpm, decisions catalog, Grafana/digest/panels/cache-invalidate counters | 3–5 | 1–4 | Kong / LiteLLM | Batteries-included day-2 on-box | Shipped |
| 8 | Full DCR; A2A; Realtime/WS; stdio MCP; M365 catalog; Skills; FIPS; HIPAA BAA | 2–4 | 3–5 | Portkey / Kong / LiteLLM / OpenAI | Demand-triggered | Watch |

Shipped this week (do not re-file): PrometheusRule alert pack; Postgres
request/event log backend; /mcp/proxy + tasks Prom parity + `mcp` modality;
per-server MCP rpm/tpm ceilings (Retry-After headers); decisions catalog on
OpenAI/Ollama discovery; Helm Grafana ConfigMap + image.digest pin; scoped
in-flight panels; cache-invalidate Prom counters; decision-guardrail async
data plane; teams metadata Postgres/export parity; concurrency caps;
hermetic RPM clock; audit reject rows.

Watch rows (do not file yet): alert-pack coverage for mcp_egress / MCP
server-reject series (file after reject-parity lands); LiteLLM 1.107 GA
docs compare (Errors tab, M365/GitHub Copilot OAuth, detect-only stream vs
buffering scanner, hosted_vllm + Databricks decisions) — stay watch until
stable; SCIM + multi-issuer/audience SSO; `gen_ai.agent.*` semconv;
per-user request-count RPD; Prometheus exemplars; decisions catalog pricing
for drex/microsoft ids; gpt-6-luna Decisions schema drift; OpenRouter BYOK
`declared_region` / IP allowlists; Anthropic Managed Agents Dynamic
Workflows + Compliance API (non-goal); Kong MCP modality cost (buyer ask);
Portkey JWT JIT (operator ask); OpenAI in-product HIPAA BAA (non-goal);
web-ui cache_invalidate table (fold into row 105/stats if operators ask).

Verified fine this run — don't re-audit: request-log PG backup catalog +
retention prune + Helm forced-backend env + doctor fleet-backend tip;
PrometheusRule expressions reference real series (no phantoms); MCP server
429 Retry-After + X-RateLimit-Scope + doctor ceilings tip; decisions on
OpenAI /v1/models + Ollama /api/tags + /api/show; cache-invalidate Prom
counters; scoped in-flight Grafana panels; Redis rate-limit outage contract
— the gap remains the **Postgres** fail-closed matrix (row 98) and erase
(row 97).

---

## Path to enterprise-grade — next 5 milestones

1. **Compliance closes the loop** — subject erasure on the PG request-log
   (row 97), the last store `daari erase` misses.
2. **Honest failure semantics** — fail-closed auth + signalled budget
   degrade + `/ready`/doctor PG probes + documented matrix (row 98).
3. **Lifecycle out of the box** — shipped OpenAI retirement calendar +
   `shutdown_date` parity so doctor/410 gates fire on install (row 99).
4. **Provable admin + MCP governance** — cache-invalidate audit (row 102),
   MCP 429 audit/Prom (row 100), member budget webhooks (row 90).
5. **Day-2 packaging + Errors forensics** — Grafana/alert for
   cache_invalidate (row 105), labeled errors by status (row 106),
   mcp_servers ceilings via Helm/editor (row 104), migrate/doctor PG
   (row 101); admin-plane rows 62–67 as sessions free up.

Compliance non-goals (SCIM, WIF depth, A2A, SOC 2 program, Realtime/WS,
FIPS builds, HIPAA BAA) stay deferred until buyer demand.

---

## Changelog

- **2026-10-14 eve (admin-surface + day-2 packaging)** — Outward: LiteLLM
  v1.107.0-dev.1 (Errors tab, Copilot OAuth providers, detect-only stream,
  hosted_vllm + Databricks decisions). Filed rows 102–106: cache-invalidate
  enterprise audit, Anthropic `decision` capability parity, mcp_servers
  rpm/tpm in config-editor + Helm, Grafana/PrometheusRule for
  cache_invalidate, labeled errors-by-status for Errors-tab parity. Morning
  rows 97–101 remain open (PG erase/outage/lifecycle/MCP reject/migrate).

- **2026-10-14 (overnight-wave parity depth)** — Marked rows 85–89 + 92–95
  Shipped (PRs #1642–#1650). Filed rows 97–101: PG request-log erasure, PG
  outage fail-closed semantics + probes, shipped model lifecycle +
  `shutdown_date` parity, MCP per-server 429 audit/Prom parity,
  migrate/doctor PG schema visibility. Outward: LiteLLM 1.105.1; OpenAI
  GPT-4 retirement wave.

- **2026-10-13 (day-2 operations depth)** — Filed rows 87–91: PrometheusRule
  alert pack, fleet-durable request/event log backend, /mcp/proxy + tasks
  Prom parity, per-member budget webhooks, BENCHMARKS DEC/SYS cross-link.
  Adopted eve-sibling rows 85–86.

- **2026-10-13 eve (day-2 observability packaging)** — Sibling scan filed
  rows 92–96; PRD PR drained to main 10-14 after pin-test failure.

- **2026-10-12 → 08-28** — Condensed: concurrency + decision-guardrail
  depth; control-plane honesty + MCP server rpm; export honesty + doctor
  ACL; team DR + console lifecycle; RBAC floors + decisions agility;
  key/end-user lifecycle; admin-plane honesty; Decisions/OAuth/multi-agent;
  governance parity; LiteLLM 1.104; Apache 2.0; this PRD's creation.
