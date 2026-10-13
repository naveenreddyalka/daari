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

## Where daari stands (verified in-tree, 2026-10-12)

**Loop velocity.** The whole 10-11 table drained in <24h again: rows 71 and
75–77/79 shipped plus the midday refill (decision guardrail kind, decisions
catalog, Helm NetworkPolicy/spread, per-key in-flight + named model map).
End-user/guardrail-profile/web-ui/report/multi-agent rows 62–63/65–67 still
`agent:working`; docs pins 72–74/78 open. Hot-reload (6) and parked Messages
tool-allowlist (7) unchanged.

**Outward.** Flat everywhere: LiteLLM **v1.105.0** stable / 1.106.0-rc.1;
Portkey v2.28.0; Kong 2.2.0; Ollama 0.40.3; vLLM 0.31.0; OpenRouter last
entry Oct 9; MCP blog Aug 22. Provider side quiet since Oct 8–9 (OpenAI
Ultrafast + SDK 3.29.0 doc chores; Anthropic Managed Agents workflows =
non-goal).

**Inward theme: depth on the 48h-old concurrency + decision-guardrail
surfaces.** Code audit verified: decision guardrails run a **sync** httpx
judgment on the event loop (and re-judge the full stream on every chunk);
chat guardrail blocks never audit; Postgres `create_team` silently drops
`max_in_flight`/model budgets that SQLite keeps; teams export omits
`metadata_json`; `max_in_flight` is settable/visible nowhere (CLI, admin
API, web-ui, Helm, Prom); Helm netpol cuts off external Redis/Postgres;
baseline suite flaked once on a wall-clock minute boundary.

---

## Scored gap table

| # | Gap | Impact | Effort | Who does it best today | Why daari wins local-first | Action |
|---|-----|:--:|:--:|------------------------|----------------------------|--------|
| 80 | Decision-guardrail data plane: async offload, bounded stream re-eval, chat audit, kind-labeled metrics | 5 | 2 | Portkey/LiteLLM guardrail hooks | $0 local judge only wins if it never stalls the loop | Filed [#1610](https://github.com/naveenreddyalka/daari/issues/1610) |
| 81 | Teams metadata parity: Postgres `create_team` + export/import round-trip (`max_in_flight`, model budgets) | 5 | 2 | LiteLLM team backup | Air-gapped restore must be the whole truth | Filed [#1611](https://github.com/naveenreddyalka/daari/issues/1611) |
| 82 | Set & see concurrency caps: CLI/admin/web-ui/Helm + per-scope in-flight gauges | 4 | 3 | LiteLLM `max_parallel_requests` admin | Watch GPU saturation on the same box | Filed [#1612](https://github.com/naveenreddyalka/daari/issues/1612) |
| 83 | Helm netpol egress for external Redis/Postgres + priorityClass/nodeSelector/tolerations/initContainers/extraEnv | 4 | 2 | Kong chart | Survive default-deny + tainted GPU pools | Filed [#1613](https://github.com/naveenreddyalka/daari/issues/1613) |
| 84 | Hermetic clock for RPM-window tests (minute-boundary flake) | 3 | 1 | — (CI trust) | Red CI must mean something | Filed [#1614](https://github.com/naveenreddyalka/daari/issues/1614) |
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
| 71 | Doctor tip when VK allowlist matches zero catalog cards | 3 | 2 | — (ops honesty) | Catch typo before BYOK clients 404 | Shipped |
| 75 | Teams export/import round-trip `cache_scope` + `priority` | 4 | 2 | LiteLLM key/team backup | Air-gapped restore keeps team tenancy | Shipped |
| 76 | Web-ui: render `last_used_at` / priority / `cache_scope` on keys+teams | 3 | 2 | OpenRouter / LiteLLM admin UI | Same-box console shows inventory fields | Shipped |
| 77 | Web-ui: honor keys `status` + `idle_days` filters | 3 | 2 | LiteLLM key hygiene UI | CLI/API filters reachable in console | Shipped |
| 79 | bench_vs_litellm: `/v1/decisions` + `/v1/systemone` scenarios | 3 | 2 | — (benchmarking) | Measure on-box Decisions vs proxy | Shipped |
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

Shipped this week (do not re-file): per-key/team/model `max_in_flight` +
named `rate_limit.models` map with 503/`Retry-After`/`X-RateLimit-Scope`;
decision-model guardrail kind; configurable decisions catalog (drex-1.5 /
microsoft-decision-1); Helm NetworkPolicy + topologySpread; teams export
`cache_scope`/`priority`; web-ui lifecycle columns + status/idle filters;
bench DEC-01/SYS-01; doctor empty-allowlist tip; filtered `/v1/models`;
key lifecycle signals; analyst role floors.

Watch rows (do not file yet): decisions catalog pricing/capabilities +
Ollama-facade visibility for drex/microsoft ids ($0 local billing is by
design — file if a hosted variant routes); BENCHMARKS.md cross-link of
DEC/SYS rows + decisions L0 cache-hit bench scenario; gpt-6-luna Decisions
schema drift; OpenRouter BYOK `declared_region` / IP allowlists (buyer
ask); Anthropic Managed Agents / Compliance API (non-goal); Kong 2.2 MCP
bundling + modality cost (buyer ask); LiteLLM 1.105/1.106 GA Lens + M365
MCP catalog (file compare features at GA); Portkey JWT JIT (operator ask);
OpenAI in-product HIPAA BAA (compliance non-goal); OpenAI 128-char safety
identifiers doc (client-side).

Verified fine this run — don't re-audit: #1605 enforcement headers + scope
labels + reject metrics + auth-and-keys/config docs; key `max_in_flight`
export via key `metadata`; keys/teams import schema refusal + CLI audit
rows; decision rules run on chat + endpoint modality paths incl. OCR/MCP;
frontier decisions ids refused for guardrails; doctor `decisions_local_models`
tip; netpol/topology chart tests; web-ui XSS-safe cells on new fields;
bench DEC/SYS unit tests + compare-doc stubs; team `max_in_flight`
enforced on SQLite path (gap is DR/Postgres/CLI/UI only).

---

## Path to enterprise-grade — next 5 milestones

1. **Guardrail data plane you can run in prod** — async decision judgments,
   bounded stream re-eval, chat-block audit parity (row 80).
2. **Fleet-store honesty** — Postgres team metadata parity + export/import
   round-trip (row 81) so #544-era Postgres fleets keep every cap.
3. **Operable concurrency** — set & observe `max_in_flight` everywhere
   (row 82) and a chart that survives real clusters (row 83).
4. **End-user + per-tenant policy** — rows 62–63 (inventory/block/cap,
   guardrail profiles) when prior sessions clear `agent:working`.
5. **Admin plane at fleet scale + FinOps truth** — web-ui pagination and
   report bounds (65–66), cost-true multi_agent pricing (67), CI trust via
   hermetic RPM windows (84).

Compliance non-goals (WIF depth, A2A, SOC 2 program, Realtime/WS, FIPS
builds, HIPAA BAA) stay deferred until buyer demand.

---

## Changelog

- **2026-10-12 (concurrency + decision-guardrail depth)** — Marked rows 71,
  75–77, 79 Shipped after the overnight drain. Filed rows 80–84: decision
  guardrail async/audit/metrics data plane, teams metadata Postgres +
  export parity, concurrency-cap ops surfaces, Helm external-backend netpol
  egress + scheduling knobs, hermetic RPM-window tests. Outward flat
  (LiteLLM 1.105.0 / Portkey 2.28.0 / Kong 2.2.0 / Ollama 0.40.3 / vLLM
  0.31.0 / OpenRouter Oct 9). Drained stale sibling PRD PR by resolving it
  to main. New watch rows: decisions catalog pricing/facade visibility,
  BENCHMARKS.md DEC/SYS cross-link.

- **2026-10-11 eve (team DR + console lifecycle + Decisions bench)** — Filed
  rows 75–79. Outward: LiteLLM 1.106 guardrail RC; Kong 2.2 GA (watch);
  llama.cpp 0.6.0 `/v1/systemone`.

- **2026-10-11 (export honesty + doctor ACL + docs pins)** — Marked rows
  60–61, 64, 68–69 Shipped. Filed rows 70–74. Outward: LiteLLM 1.105 rc.3
  Decisions; Ollama 0.40.3.

- **2026-10-10 → 08-28** — Condensed: key/end-user lifecycle; admin-plane
  honesty; Decisions/OAuth/multi-agent; governance parity; LiteLLM 1.104;
  Apache 2.0; this PRD's creation.
