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

## Where daari stands (verified in-tree, 2026-10-11)

**Loop velocity.** Eve feeder rows 65–67 (web-ui / report bounds / multi_agent
model pricing) and end-user/guardrail rows 62–63 remain open with
`agent:working` from prior sessions. Catalog ACL (69), key hygiene (60–61),
retired observability (64), and decisions L0 tenancy pin (68) drained on
main. Hot-reload (6) and parked Messages tool-allowlist (7) unchanged.

**Outward.** LiteLLM stable bar still **v1.104.x**; **1.105** at rc.3 adds
proxy Decisions (`/v1/decisions` + `/v1/systemone`) — daari already ships both
on-box (compare refresh filed). Ollama **0.40.3** (launcher warning cleanup +
paused background model upgrades). Portkey / Kong / vLLM flat vs prior scan.

**Inward theme: export honesty + doctor ACL + docs pins.** Code audit: keys
export omits `last_used_at` / `priority` / `cache_scope`; doctor never tips
when a VK allowlist matches zero catalog cards; `daari stats --help` omits
`virtual_keys`; compare-litellm still watches RC.1 only; virtual-keys catalog
ACL doc has no hermetic pin.

---

## Scored gap table

| # | Gap | Impact | Effort | Who does it best today | Why daari wins local-first | Action |
|---|-----|:--:|:--:|------------------------|----------------------------|--------|
| 70 | Keys export/import round-trip `last_used_at` + priority + cache_scope | 4 | 2 | LiteLLM key backup | Air-gapped restore keeps idle/admission | Shipped [#1586](https://github.com/naveenreddyalka/daari/pull/1586) |
| 71 | Doctor tip when VK allowlist matches zero catalog cards | 3 | 2 | — (ops honesty) | Catch typo before BYOK clients 404 | Filed [#1582](https://github.com/naveenreddyalka/daari/issues/1582) |
| 72 | `daari stats --help` mentions `virtual_keys` | 2 | 1 | — (CLI honesty) | Same JSON operators already dump | Filed [#1583](https://github.com/naveenreddyalka/daari/issues/1583) |
| 73 | compare-litellm: LiteLLM 1.105 RC Decisions vs daari | 2 | 1 | LiteLLM release notes | On-box Decisions already ship | Filed [#1584](https://github.com/naveenreddyalka/daari/issues/1584) |
| 74 | Hermetic pin: virtual-keys.md documents `/v1/models` allowlist | 2 | 1 | — (docs regression) | Keep ACL sentence in CI | Filed [#1585](https://github.com/naveenreddyalka/daari/issues/1585) |
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
| 55–59 | Decisions budgets; Ultrafast; haiku fidelity; lifecycle; revoked-jti pool | 4–5 | 2 | LiteLLM / OpenAI / Kong | On-box parity | Shipped |
| 44–52 | Decisions facade; MCP OAuth denylist; admin pagination; multi_agent meter | 4–5 | 2–3 | Portkey / Kong / LiteLLM | On-box parity | Shipped |
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
`--status`/`--idle-days` docs/help pins; regional-processing 1.10×; audit
pagination; Ultrafast/Fast tiers; Anthropic lifecycle cards.

Watch rows (do not file yet): gpt-6-luna Decisions schema drift; OpenRouter
BYOK `declared_region` / IP allowlists (buyer ask); Anthropic Managed Agents
/ Compliance API (non-goal); LiteLLM 1.105 GA Lens + M365 MCP catalog (file
compare features at GA — Decisions RC note already filed); Portkey JWT JIT
(operator ask); OpenAI in-product HIPAA BAA (compliance non-goal).

Verified fine this run — don't re-audit: filtered catalog on OpenAI facade;
`last_used_at` touch + CLI filters; key_expiry doctor + Prom + webhook;
retired rejects metric + doctor; decisions L0 tenancy hermetic; stats
`virtual_keys` + Grafana panels; regional-processing uplift; MCP grant
fail-closed; compact-to-fit telemetry.

---

## Path to enterprise-grade — next 5 milestones

1. **Credential backup honesty** — export/import lifecycle + admission fields
   (row 70) so DR keeps idle hygiene and priority.
2. **Admin plane at fleet scale** — drain web-ui `has_more` / `report.users`
   (65) and bounded report rollups (66) still open from the eve feeder.
3. **End-user + per-tenant policy** — rows 62–63 (inventory/block/cap,
   guardrail profiles) when prior sessions clear `agent:working`.
4. **FinOps depth** — cost-true multi_agent nested models (67); doctor empty
   allowlist tip (71).
5. **Operate without restart** — config hot-reload (6) and parked Messages
   tool allowlist (7) when a long session is available.

Compliance non-goals (WIF depth, A2A, SOC 2 program, Realtime/WS, FIPS
builds, HIPAA BAA) stay deferred until buyer demand.

---

## Changelog

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
