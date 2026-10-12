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

## Where daari stands (verified in-tree, 2026-10-12 eve)

**Loop velocity.** Midday refill (rows 80–84) still open; overnight 10-11
drain (71, 75–77, 79) stays Shipped. End-user/guardrail-profile/web-ui/
report/multi-agent rows 62–63/65–67 still `agent:working`; docs pins
72–74/78 open. Hot-reload (6) and parked Messages tool-allowlist (7)
unchanged.

**Outward.** Still flat: LiteLLM **v1.105.0** stable / **1.106.0-rc.1**
(MCP server-level rpm, Lens Rust service, Admin Home — no GA). Portkey
enterprise changelog tops at older 2.x Unified Gateway+MCP notes (no new
tag vs midday). Kong AI Gateway **2.2** passthrough for vLLM/Ollama
unchanged. Ollama 0.40.3; vLLM 0.31.0; OpenRouter last entry Oct 9.

**Inward theme: control-plane honesty on the surfaces we just shipped.**
Code audit verified: soft RPM warning is dropped when a concurrency gauge
wins the binding; budget 402 / rate-limit 429 / concurrency 503 never write
audit rows; `/v1/systemone` lacks Idempotency-Key parity with `/v1/decisions`;
local decisions catalog (incl. drex/microsoft) is invisible on `/v1/models`
and Ollama `/api/tags`; `McpServerSettings` has no per-server rpm/tpm while
LiteLLM 1.106 rc added server-level MCP rpm.

---

## Scored gap table

| # | Gap | Impact | Effort | Who does it best today | Why daari wins local-first | Action |
|---|-----|:--:|:--:|------------------------|----------------------------|--------|
| 85 | Audit ledger for budget 402 + rate-limit/concurrency rejects | 5 | 2 | LiteLLM/Portkey deny callbacks | Air-gapped deny trail next to the usage ledger | Filed [#1616](https://github.com/naveenreddyalka/daari/issues/1616) |
| 86 | Keep soft rate-limit warning when concurrency gauge binding wins | 4 | 2 | LiteLLM soft budget headers | Early load-shed on-box even with in-flight caps | Filed [#1617](https://github.com/naveenreddyalka/daari/issues/1617) |
| 87 | `/v1/systemone` Idempotency-Key parity with `/v1/decisions` | 4 | 2 | LiteLLM systemone retries | Safe retry for local judges without double-meter | Filed [#1618](https://github.com/naveenreddyalka/daari/issues/1618) |
| 88 | Advertise local decisions catalog on `/v1/models` + Ollama `/api/tags` | 4 | 2 | LiteLLM model list / Ollama tags | IDE discovers on-box judges without hardcoding | Filed [#1619](https://github.com/naveenreddyalka/daari/issues/1619) |
| 89 | Per-server rpm/tpm on `integrations.mcp_servers` | 4 | 3 | LiteLLM 1.106 MCP server rpm | Cap noisy egress MCP without cutting the whole key | Filed [#1620](https://github.com/naveenreddyalka/daari/issues/1620) |
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
| 8 | Full DCR; A2A; Realtime/WS; stdio MCP; M365 catalog; Skills; FIPS; HIPAA BAA | 2–4 | 3–5 | Portkey / Kong / LiteLLM / OpenAI | Demand-triggered | Watch |

Shipped this week (do not re-file): per-key/team/model `max_in_flight` +
named `rate_limit.models` map; decision-model guardrail kind; configurable
decisions catalog; Helm NetworkPolicy + topologySpread; teams export
`cache_scope`/`priority`; web-ui lifecycle columns + status/idle filters;
bench DEC-01/SYS-01; doctor empty-allowlist tip; filtered `/v1/models`;
key lifecycle signals; analyst role floors; compact-to-fit + MCP
fail-closed suite from prior days.

Watch rows (do not file yet): BENCHMARKS.md cross-link of DEC/SYS rows +
decisions L0 cache-hit bench scenario; unknown-model error string still
lists only clef/nimble/tev1 (file next if not folded into catalog
discovery); Postgres `VirtualKeyStore.create` omits `max_in_flight` kwarg
(sibling of team-metadata Postgres gap — file after that lands);
Prom/Grafana modality-labeled Decisions L0 panel; doctor tip for
`kind=decision` guardrails without a runnable local path; gpt-6-luna
Decisions schema drift; OpenRouter BYOK `declared_region` / IP allowlists
(buyer ask);
Anthropic Managed Agents / Compliance API (non-goal); Kong 2.2 MCP
bundling + modality cost (buyer ask); LiteLLM 1.106 GA Lens + M365 MCP
catalog (file compare at GA); Portkey JWT JIT (operator ask); OpenAI
HIPAA BAA / 128-char safety identifiers (non-goal / client-side).

Verified fine this run — don't re-audit: midday rows 80–84 still correctly
scoped (async guardrail, team PG metadata, concurrency ops surfaces, Helm
egress, hermetic RPM clock); local drex/microsoft billing intentionally
`$0`; key export already round-trips key `metadata_json` incl.
`max_in_flight`; family-level `mcp` RPM exists (gap is per-server only);
chat guardrail audit depth stays under row 80.

---

## Path to enterprise-grade — next 5 milestones

1. **Deny ledger you can defend** — audit rows for budget/rate/concurrency
   rejects (row 85) plus guardrail chat-block audit (row 80).
2. **Honest concurrency + soft warnings** — keep soft RPM signal when
   in-flight gauges win (row 86); set & observe caps (row 82).
3. **Decisions discovery + safe retries** — catalog on model facades
   (row 88) and systemone Idempotency-Key parity (row 87).
4. **Fleet-store + chart honesty** — Postgres team metadata (row 81),
   Helm external-backend netpol (row 83), MCP per-server rpm (row 89).
5. **End-user + per-tenant policy** — rows 62–63 when prior sessions clear
   `agent:working`; admin pagination / FinOps (65–67) and hermetic RPM
   windows (84) close the loop.

Compliance non-goals (WIF depth, A2A, SOC 2 program, Realtime/WS, FIPS
builds, HIPAA BAA) stay deferred until buyer demand.

---

## Changelog

- **2026-10-12 eve (control-plane honesty + MCP server rpm)** — Outward
  still flat (LiteLLM 1.105.0 / 1.106.0-rc.1 MCP server rpm + Lens Rust;
  Portkey/Kong/Ollama/vLLM unchanged). Filed rows 85–89: audit on
  budget/rate/concurrency rejects, soft warning vs concurrency binding,
  systemone Idempotency-Key parity, decisions catalog on `/v1/models` +
  Ollama tags, per-server MCP rpm/tpm. Promoted prior watch
  (catalog visibility) into row 88; left BENCHMARKS DEC/SYS, PG key
  `max_in_flight` create kwarg, Prom Decisions L0, and doctor
  `kind=decision` tip as watch. Pruned compact-to-fit shipped rows 19–28
  into the weekly shipped blurb.

- **2026-10-12 (concurrency + decision-guardrail depth)** — Marked rows 71,
  75–77, 79 Shipped. Filed rows 80–84. Outward flat (LiteLLM 1.105.0 /
  Portkey 2.28.0 / Kong 2.2.0 / Ollama 0.40.3 / vLLM 0.31.0).

- **2026-10-11 eve (team DR + console lifecycle + Decisions bench)** — Filed
  rows 75–79. Outward: LiteLLM 1.106 guardrail RC; Kong 2.2 GA (watch);
  llama.cpp 0.6.0 `/v1/systemone`.

- **2026-10-11 (export honesty + doctor ACL + docs pins)** — Marked rows
  60–61, 64, 68–69 Shipped. Filed rows 70–74. Outward: LiteLLM 1.105 rc.3
  Decisions; Ollama 0.40.3.

- **2026-10-10 → 08-28** — Condensed: key/end-user lifecycle; admin-plane
  honesty; Decisions/OAuth/multi-agent; governance parity; LiteLLM 1.104;
  Apache 2.0; this PRD's creation.
