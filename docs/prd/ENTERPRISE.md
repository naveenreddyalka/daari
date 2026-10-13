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

## Where daari stands (verified in-tree, 2026-10-13)

**Loop velocity.** The whole 10-12 table drained in <24h again: rows 80–84
(decision-guardrail data plane, teams metadata parity, concurrency-cap ops
surfaces, Helm external-backend egress + scheduling, hermetic RPM clock)
all shipped, plus the eve sibling's audit-reject rows and systemone
Idempotency-Key. End-user/guardrail-profile/web-ui/report/multi-agent rows
62–63/65–67 still `agent:working`; docs pins 72–74/78 open; eve rows 85–86
(decisions catalog advertising, per-MCP-server rpm/tpm) open.

**Outward.** Flat everywhere: LiteLLM v1.105.0 stable / 1.106.0-rc.1;
Portkey v2.28.0; Kong 2.2.0; Ollama 0.40.3 (0.40.4-rc1 prerelease); vLLM
0.31.0; OpenRouter last entry Oct 9; MCP blog Aug 22. Provider side quiet
since Oct 8–9 (OpenAI Ultrafast; Anthropic Managed Agents workflows =
non-goal).

**Inward theme: day-2 operations depth.** Code audit verified: the
request/event log is the **last per-pod-only store** (JSONL + best-effort
OTLP emit; every other store has Redis/Postgres); the Helm chart ships
scrape + dashboards but **zero alert rules** despite rich failure-mode
metrics; `POST /mcp/proxy` and MCP tasks record no Prometheus request
series and proxy spans masquerade as `chat` (`"mcp"` missing from the
modality map); SSO is single issuer/audience with login-time-only
deprovisioning and no SCIM; budget webhooks stop at key/team scope.

---

## Scored gap table

| # | Gap | Impact | Effort | Who does it best today | Why daari wins local-first | Action |
|---|-----|:--:|:--:|------------------------|----------------------------|--------|
| 87 | Shipped PrometheusRule alert pack: breaker/budget/5xx/queue/guardrails/key-expiry | 5 | 2 | LiteLLM alerting docs / Kong | Batteries-included day-2 ops on-box | Filed [#1630](https://github.com/naveenreddyalka/daari/issues/1630) |
| 88 | Fleet-durable request/event log backend (postgres\|redis) — last per-pod store | 5 | 4 | LiteLLM DB spend logs | Air-gapped fleets need on-box durability | Filed [#1631](https://github.com/naveenreddyalka/daari/issues/1631) |
| 89 | /mcp/proxy + MCP tasks Prom parity; register `mcp` modality (spans report `chat` today) | 4 | 2 | Kong MCP analytics / LiteLLM | One governed MCP door must be observable | Filed [#1632](https://github.com/naveenreddyalka/daari/issues/1632) |
| 90 | Per-member budget threshold webhooks on shared team keys | 3 | 3 | LiteLLM 1.105 member alerts | Catch a runaway agent via the on-box ledger | Filed [#1633](https://github.com/naveenreddyalka/daari/issues/1633) |
| 91 | BENCHMARKS.md DEC/SYS cross-link + decisions L0 cache-hit scenario | 3 | 1 | — (benchmarking honesty) | Publish the on-box warm-judgment win | Filed [#1634](https://github.com/naveenreddyalka/daari/issues/1634) |
| 85 | Advertise local decisions catalog on `/v1/models` + Ollama `/api/tags` | 3 | 2 | LiteLLM 1.106 decisions UI | BYOK clients discover on-box judges | Open |
| 86 | Per-server rpm/tpm ceilings on `integrations.mcp_servers` | 4 | 2 | LiteLLM MCP limits | Protect small MCP backends from one tenant | Open |
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
| 80 | Decision-guardrail data plane: async offload, bounded stream re-eval, chat audit, kind-labeled metrics | 5 | 2 | Portkey/LiteLLM guardrail hooks | $0 local judge only wins if it never stalls the loop | Shipped |
| 81 | Teams metadata parity: Postgres `create_team` + export/import round-trip (`max_in_flight`, model budgets) | 5 | 2 | LiteLLM team backup | Air-gapped restore must be the whole truth | Shipped |
| 82 | Set & see concurrency caps: CLI/admin/web-ui/Helm + per-scope in-flight gauges | 4 | 3 | LiteLLM `max_parallel_requests` admin | Watch GPU saturation on the same box | Shipped |
| 83 | Helm netpol egress for external Redis/Postgres + priorityClass/nodeSelector/tolerations/initContainers/extraEnv | 4 | 2 | Kong chart | Survive default-deny + tainted GPU pools | Shipped |
| 84 | Hermetic clock for RPM-window tests (minute-boundary flake) | 3 | 1 | — (CI trust) | Red CI must mean something | Shipped |
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

Shipped this week (do not re-file): decision-guardrail async data plane +
chat audit + kind metrics; teams metadata Postgres/export parity; concurrency
caps across CLI/admin/web-ui/Helm/Prom; Helm external Redis/Postgres egress +
scheduling knobs; hermetic RPM clock; audit rows for budget 402 and
rate-limit/concurrency rejects; systemone Idempotency-Key; teams export
`cache_scope`/`priority`; web-ui lifecycle columns + filters; bench
DEC-01/SYS-01; doctor empty-allowlist tip; analyst role floors.

Watch rows (do not file yet): SCIM provisioning + multi-issuer/audience SSO
(groups→team sync + revoke happen only at next login — file on
regulated-buyer ask); `gen_ai.agent.*` semconv spans for multi_agent
(conversation.id ships; agent spans on OTel semconv demand); per-user
request-count RPD beyond `user_daily_usd_cap` (buyer ask); Prometheus
exemplars on hand-rolled histograms (tracing-correlation ask); decisions
catalog pricing/capabilities for drex/microsoft ids ($0 local by design —
file if a hosted variant routes); gpt-6-luna Decisions schema drift;
OpenRouter BYOK `declared_region` / IP allowlists (buyer ask); Anthropic
Managed Agents / Compliance API (non-goal); Kong 2.2 MCP bundling +
modality cost (buyer ask); LiteLLM 1.106 GA Lens + M365 MCP catalog
(compare rows at GA); Portkey JWT JIT (operator ask); OpenAI in-product
HIPAA BAA (compliance non-goal); OpenAI 128-char safety identifiers doc
(client-side).

Verified fine this run — don't re-audit: request-log rotation + retention
prune + stdout mirror + OTLP emit (gap is shared backend only); backup
catalogs request-log JSONL incl. rotated files; budget + key-expiry
webhooks signed and Redis-deduped; MCP ingress tools/call + egress Prom
counters; OCR/systemone/decisions all have Prom + OTel + ledger parity;
multi-JWKS SSO + groups→team sync + unmapped-deny revoke at login;
`gen_ai.conversation.id` emitted from session_id; bench DEC-01/SYS-01
judgment timing exists (gap is doc cross-link + L0-hit scenario only).

---

## Path to enterprise-grade — next 5 milestones

1. **Alerting out of the box** — PrometheusRule pack for breaker, budget,
   5xx, queue depth, guardrails, key expiry (row 87).
2. **Fleet log durability** — request/event log on Postgres/Redis so two
   replicas tell one story and `daari backup` is the whole truth (row 88).
3. **Observable MCP door** — Prom parity + honest `mcp` operation name on
   /mcp/proxy and tasks (row 89), per-server MCP ceilings (row 86).
4. **End-user + per-tenant policy** — rows 62–63 (inventory/block/cap,
   guardrail profiles) when prior sessions clear `agent:working`, member
   budget webhooks (row 90).
5. **Admin plane at fleet scale + proof** — web-ui pagination and report
   bounds (65–66), cost-true multi_agent pricing (67), published decisions
   L0 benchmark (row 91), decisions catalog discovery (row 85).

Compliance non-goals (SCIM, WIF depth, A2A, SOC 2 program, Realtime/WS,
FIPS builds, HIPAA BAA) stay deferred until buyer demand.

---

## Changelog

- **2026-10-13 (day-2 operations depth)** — Marked rows 80–84 Shipped after
  the overnight drain; adopted eve-sibling rows 85–86 (its PRD PR was
  superseded and drained to main). Filed rows 87–91: shipped PrometheusRule
  alert pack, fleet-durable request/event log backend, /mcp/proxy + tasks
  Prom parity with `mcp` modality fix, per-member budget webhooks,
  BENCHMARKS DEC/SYS cross-link + decisions L0-hit scenario. Outward flat
  (LiteLLM 1.105.0 / Portkey 2.28.0 / Kong 2.2.0 / Ollama 0.40.3 / vLLM
  0.31.0 / OpenRouter Oct 9 / MCP Aug 22). New watch rows: SCIM +
  multi-issuer SSO, gen_ai.agent.* semconv, per-user RPD, Prom exemplars.

- **2026-10-12 (concurrency + decision-guardrail depth)** — Filed rows
  80–84: decision guardrail async/audit/metrics data plane, teams metadata
  Postgres + export parity, concurrency-cap ops surfaces, Helm
  external-backend netpol egress + scheduling knobs, hermetic RPM-window
  tests. Drained stale sibling PRD PR by resolving it to main.

- **2026-10-12 eve (control-plane honesty + MCP server rpm)** — Sibling scan
  filed rows 85–86 and audit-reject/systemone follow-ups; its PRD PR failed
  the pin test and was drained to main (rows adopted 10-13).

- **2026-10-11 → 08-28** — Condensed: export honesty + doctor ACL; team DR
  + console lifecycle + Decisions bench; RBAC floors + decisions agility;
  key/end-user lifecycle; admin-plane honesty; Decisions/OAuth/multi-agent;
  governance parity; LiteLLM 1.104; Apache 2.0; this PRD's creation.
