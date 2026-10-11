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

## Where daari stands (verified in-tree, 2026-10-11 eve)

**Loop velocity.** Eve feeder rows 65–67 (web-ui / report bounds / multi_agent
pricing) and end-user/guardrail rows 62–63 still `agent:working`. Midday
filed doctor/stats/compare pins (71–74) plus guardrail/decisions catalog /
Helm NetworkPolicy / per-key in-flight (separate midday refill) remain open.
Keys export lifecycle fields (70) and RBAC analyst floors on ungated
`/v1/daari` read surfaces shipped. Hot-reload (6) and parked Messages
tool-allowlist (7) unchanged.

**Outward.** LiteLLM stable bar still **v1.104.x**; **1.105** at rc.3
(Decisions on proxy); **1.106** RC/backport adds decision-model guardrail
(compare note filed). Ollama **0.40.3** flat. Kong AI Gateway **2.2** GA
(MCP bundling, modality-aware cost, identity-keyed policies) — watch only
until buyer ask. llama.cpp **0.6.0** ships `/v1/systemone` (daari already
has the facade). Portkey / OpenRouter / vLLM / GPTCache flat vs prior scan.

**Inward theme: team DR honesty + admin-console lifecycle + Decisions
bench.** Code audit: teams export omits `cache_scope`/`priority` (keys fixed);
web-ui ignores inventory fields and `status`/`idle_days` query params;
compare-litellm still watches 1.105-rc.1 only; `bench_vs_litellm` has no
Decisions/System One rows.

---

## Scored gap table

| # | Gap | Impact | Effort | Who does it best today | Why daari wins local-first | Action |
|---|-----|:--:|:--:|------------------------|----------------------------|--------|
| 75 | Teams export/import round-trip `cache_scope` + `priority` | 4 | 2 | LiteLLM key/team backup | Air-gapped restore keeps team tenancy | Filed [#1595](https://github.com/naveenreddyalka/daari/issues/1595) |
| 76 | Web-ui: render `last_used_at` / priority / `cache_scope` on keys+teams | 3 | 2 | OpenRouter / LiteLLM admin UI | Same-box console shows inventory fields | Filed [#1596](https://github.com/naveenreddyalka/daari/issues/1596) |
| 77 | Web-ui: honor keys `status` + `idle_days` filters | 3 | 2 | LiteLLM key hygiene UI | CLI/API filters reachable in console | Filed [#1597](https://github.com/naveenreddyalka/daari/issues/1597) |
| 78 | compare-litellm: LiteLLM 1.106 decision-model guardrail watch | 2 | 1 | LiteLLM release notes | Honest local-first positioning | Filed [#1598](https://github.com/naveenreddyalka/daari/issues/1598) |
| 79 | bench_vs_litellm: `/v1/decisions` + `/v1/systemone` scenarios | 3 | 2 | — (benchmarking) | Measure on-box Decisions vs proxy | Filed [#1599](https://github.com/naveenreddyalka/daari/issues/1599) |
| 70 | Keys export/import round-trip `last_used_at` + priority + cache_scope | 4 | 2 | LiteLLM key backup | Air-gapped restore keeps idle/admission | Shipped |
| 71 | Doctor tip when VK allowlist matches zero catalog cards | 3 | 2 | — (ops honesty) | Catch typo before BYOK clients 404 | Open |
| 72 | `daari stats --help` mentions `virtual_keys` | 2 | 1 | — (CLI honesty) | Same JSON operators already dump | Open |
| 73 | compare-litellm: LiteLLM 1.105 RC Decisions vs daari | 2 | 1 | LiteLLM release notes | On-box Decisions already ship | Open |
| 74 | Hermetic pin: virtual-keys.md documents `/v1/models` allowlist | 2 | 1 | — (docs regression) | Keep ACL sentence in CI | Open |
| 69 | Filter `GET /v1/models` by VK `allowed_models` | 5 | 2 | OpenRouter filtered catalog | Same allowlist as inference | Shipped |
| 65 | Web-ui: honor keys/teams `has_more` + render `report.users` | 4 | 2 | LiteLLM admin UI | Same-box console finishes the job | Open |
| 66 | Bound/paginate report `clients`/`users` rollups | 4 | 2 | LiteLLM paged usage | Fleet-safe JSON on-box | Open |
| 67 | multi_agent nested usage: per-subagent `model` for cost-true pricing | 4 | 2 | OpenAI / LiteLLM FinOps | Ledger already meters nested tokens | Open |
| 68 | Hermetic decisions L0 `cache_scope` tenancy test | 3 | 1 | — (testability) | Prove typed-judgment isolation | Shipped |
| 60 | `last_used_at` on virtual keys + status/idle list filters | 4 | 2 | OpenRouter keys API | Key hygiene on-box, air-gapped | Shipped |
| 61 | Proactive key-expiry signals: doctor scan, Prom gauge, signed webhook | 4 | 2 | OpenRouter / LiteLLM alerts | Same store that enforces warns | Shipped |
| 62 | End-user inventory + per-user block/cap overrides | 5 | 3 | OpenRouter end-users / LiteLLM | Ledger already knows every user | Open |
| 63 | Named guardrail profiles bindable per key/team | 5 | 3 | OpenRouter guardrail assign / Portkey | Per-tenant policy, zero hops | Open |
| 64 | Audit + metric on retired-model blocks; doctor lifecycle check | 3 | 2 | LiteLLM audit planes | Catalog + router + audit in one box | Shipped |
| 6 | Hot-reload `config.yaml` | 3 | 2 | LiteLLM config ownership | Open — needs long session | Open |
| 7 | Per-key tool-name allowlist for Messages `mcp_servers` | 4 | 3 | LiteLLM `mcp_tool_permissions` | Parked (needs ≥60m session) | Parked |
| 53 | Doctor + Helm + auth-and-keys coverage for `/v1/decisions` | 3 | 1 | — (ops honesty) | Operators discover the surface | Shipped |
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

Shipped this week (do not re-file): filtered `/v1/models` catalog; key
`last_used_at` + idle filters; key-expiry doctor/gauge/webhook; retired-block
audit/metric/doctor; decisions L0 `cache_scope` hermetic pin; stats
`virtual_keys`; Grafana virtual_keys + retired panels; keys list CLI
`--status`/`--idle-days` docs/help pins; keys export lifecycle fields;
analyst role floors on ungated `/v1/daari` read/feedback; regional-processing
1.10×; audit pagination; Ultrafast/Fast tiers; Anthropic lifecycle cards.

Watch rows (do not file yet): gpt-6-luna Decisions schema drift; OpenRouter
BYOK `declared_region` / IP allowlists (buyer ask); Anthropic Managed Agents
/ Compliance API (non-goal); Kong 2.2 MCP bundling + modality cost (buyer
ask); LiteLLM 1.105/1.106 GA Lens + M365 MCP catalog (file compare features
at GA — Decisions RC + 1.106 guardrail notes already filed); Portkey JWT JIT
(operator ask); OpenAI in-product HIPAA BAA (compliance non-goal).

Verified fine this run — don't re-audit: filtered catalog on OpenAI facade;
`last_used_at` touch + CLI filters; key export key-row fields; key_expiry
doctor + Prom + webhook; retired rejects metric + doctor; decisions L0
tenancy hermetic; stats `virtual_keys` + Grafana panels; analyst floors on
route/preview / cache/diversity / learn/stats / feedback; MCP grant
fail-closed; compact-to-fit telemetry; `/v1/systemone` facade.

---

## Path to enterprise-grade — next 5 milestones

1. **Credential backup honesty (teams)** — export/import team
   `cache_scope`/`priority` (row 75) so DR matches key-row lifecycle fields.
2. **Admin plane at fleet scale** — drain web-ui `has_more` / `report.users`
   (65), bounded report rollups (66), and console lifecycle columns/filters
   (76–77).
3. **End-user + per-tenant policy** — rows 62–63 (inventory/block/cap,
   guardrail profiles) when prior sessions clear `agent:working`.
4. **FinOps + Decisions proof** — cost-true multi_agent nested models (67);
   Decisions/System One bench rows (79).
5. **Operate without restart** — config hot-reload (6) and parked Messages
   tool allowlist (7) when a long session is available.

Compliance non-goals (WIF depth, A2A, SOC 2 program, Realtime/WS, FIPS
builds, HIPAA BAA) stay deferred until buyer demand.

---

## Changelog

- **2026-10-11 eve (team DR + console lifecycle + Decisions bench)** — Marked
  row 70 Shipped. Filed rows 75–79: teams export `cache_scope`/`priority`,
  web-ui lifecycle columns, web-ui status/idle filters, compare-litellm 1.106
  decision-model guardrail watch, bench_vs_litellm Decisions/System One.
  Outward: LiteLLM 1.106 guardrail RC; Kong AI Gateway 2.2 GA (watch);
  llama.cpp 0.6.0 `/v1/systemone`. Pruned dense shipped summary; kept open
  midday rows 71–74.

- **2026-10-11 (export honesty + doctor ACL + docs pins)** — Marked rows
  60–61, 64, 68–69 Shipped after Oct 10–11 drain. Filed rows 70–74: keys
  export lifecycle fields, doctor empty-allowlist tip, stats help
  `virtual_keys`, compare-litellm Decisions RC note, virtual-keys catalog
  ACL hermetic pin. Outward: LiteLLM 1.105 rc.3 Decisions; Ollama 0.40.3.
  Pruned dense shipped rows 49–59 into summary lines to stay under ~300.

- **2026-10-10 eve (admin-plane honesty + FinOps + catalog ACL)** — Filed
  rows 65–69. Outward: LiteLLM 1.105 RC; OpenRouter filtered-catalog parity.

- **2026-10-10 pm (key + end-user lifecycle governance)** — Filed rows
  60–64 after OpenRouter admin-plane wave; row 53 Shipped.

- **2026-10-10 → 08-28** — Condensed: Decisions/OAuth/admin/multi-agent;
  governance parity; LiteLLM 1.104; Apache 2.0; this PRD's creation.
