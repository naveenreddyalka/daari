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

**Loop velocity.** The 10-10 pm/eve tables are mostly drained in under 24h:
rows 60, 61, 64, 68, 69 shipped overnight plus keys export/import round-trip;
rows 62, 63, 65–67 are in flight (`agent:working`). Hot-reload (6) and the
parked Messages tool-allowlist (7) are unchanged.

**Outward.** **LiteLLM v1.105.0 went STABLE today (2026-10-11)**: Lens/agent
traces GA, opt-in `fail_closed_rate_limit_enforcement` (503 when Redis
counters are unreachable), guardrail execution time bounds + SSRF blocking on
guardrail HTTP calls, team-member budget percentage alerts, MCP protocol-version
configuration, and Rust config/router/gateway crates (performance positioning).
v1.106.0-rc.1 backports **Microsoft-Decision-1**, a **decision-model guardrail**,
and a decisions admin UI. Other bars flat: Portkey v2.28.0 (changelog pages
serving stale snapshots again), Kong 2.2.0, vLLM 0.31.0, Ollama 0.40.3
(trivial fixes), OpenRouter quiet since the Oct 6–9 admin-plane wave. Provider
side: **open-weight decision models arrived** — Nace AI Drex 1.5 (9B, single
forward pass, 128K ctx) and Microsoft-Decision-1 (9B, Qwen 3.5-derived);
OpenAI Agents API public beta opened to all (platform-side harness).

**Inward theme: admin-plane RBAC honesty + decisions-ecosystem agility +
fleet-chart depth.** Code audit: four `/v1/daari/*` surfaces enforce no role
floor (`route/preview`, `cache/diversity`, `learn/stats`, and `feedback`,
which lets any bearer poison org-learning training data); guardrails are
regex-only with no local decision-model judge; the local decisions catalog is
a hardcoded frozenset that would reject Drex 1.5; the Helm chart has no
NetworkPolicy or topology-spread knobs; concurrency caps are global-only with
one flat per-model ceiling.

---

## Scored gap table

| # | Gap | Impact | Effort | Who does it best today | Why daari wins local-first | Action |
|---|-----|:--:|:--:|------------------------|----------------------------|--------|
| 70 | Role floors on ungated `/v1/daari` reads + feedback poisoning | 4 | 1 | LiteLLM mgmt-route matrix | Role check + audit live on-box | Filed [#1588](https://github.com/naveenreddyalka/daari/issues/1588) |
| 71 | Local decision-model guardrail check (judge via decisions models) | 5 | 3 | LiteLLM 1.106-rc decision guardrail | Zero-egress judge on own GPU | Filed [#1589](https://github.com/naveenreddyalka/daari/issues/1589) |
| 72 | Configurable decisions catalog + drex-1.5 / microsoft-decision-1 | 4 | 2 | LiteLLM 1.106-rc | New judges = config edit, not release | Filed [#1590](https://github.com/naveenreddyalka/daari/issues/1590) |
| 73 | Helm NetworkPolicy + topologySpread/anti-affinity knobs | 4 | 2 | Kong/Portkey charts | Pass platform security review stock | Filed [#1591](https://github.com/naveenreddyalka/daari/issues/1591) |
| 74 | Per-key max in-flight + named per-model rate/concurrency map | 4 | 2 | LiteLLM `max_parallel_requests` / Kong credential RL | Protect local GPU tiers directly | Filed [#1592](https://github.com/naveenreddyalka/daari/issues/1592) |
| 62 | End-user inventory + per-user block/cap overrides | 5 | 3 | OpenRouter end-users / LiteLLM | Ledger already knows every user | Filed [#1547](https://github.com/naveenreddyalka/daari/issues/1547) |
| 63 | Named guardrail profiles bindable per key/team | 5 | 3 | OpenRouter guardrail assign / Portkey | Per-tenant policy, zero hops | Filed [#1548](https://github.com/naveenreddyalka/daari/issues/1548) |
| 65 | Web-ui: honor keys/teams `has_more` + render `report.users` | 4 | 2 | LiteLLM admin UI | Same-box console finishes the job | Filed [#1551](https://github.com/naveenreddyalka/daari/issues/1551) |
| 66 | Bound/paginate report `clients`/`users` rollups | 4 | 2 | LiteLLM paged usage | Fleet-safe JSON on-box | Filed [#1552](https://github.com/naveenreddyalka/daari/issues/1552) |
| 67 | multi_agent nested usage: per-subagent `model` for cost-true pricing | 4 | 2 | OpenAI / LiteLLM FinOps | Ledger already meters nested tokens | Filed [#1553](https://github.com/naveenreddyalka/daari/issues/1553) |
| 6 | Hot-reload `config.yaml` | 3 | 2 | LiteLLM config ownership | Open — needs long session | Open [#1234](https://github.com/naveenreddyalka/daari/issues/1234) |
| 7 | Per-key tool-name allowlist for Messages `mcp_servers` | 4 | 3 | LiteLLM `mcp_tool_permissions` | Parked (needs ≥60m session) | Parked [#1288](https://github.com/naveenreddyalka/daari/issues/1288) |
| 69 | Filter `GET /v1/models` by VK `allowed_models` | 5 | 2 | OpenRouter filtered catalog | Same allowlist as inference | Shipped [#1557](https://github.com/naveenreddyalka/daari/pull/1557) |
| 60 | `last_used_at` on virtual keys + status/idle list filters | 4 | 2 | OpenRouter keys API | Key hygiene on-box, air-gapped | Shipped [#1558](https://github.com/naveenreddyalka/daari/pull/1558) |
| 61 | Proactive key-expiry signals: doctor scan, Prom gauge, signed webhook | 4 | 2 | OpenRouter / LiteLLM alerts | Same store that enforces warns | Shipped [#1560](https://github.com/naveenreddyalka/daari/pull/1560) |
| 64 | Audit + metric on retired-model blocks; doctor lifecycle check | 3 | 2 | LiteLLM audit planes | Catalog + router + audit in one box | Shipped [#1561](https://github.com/naveenreddyalka/daari/pull/1561) |
| 68 | Hermetic decisions L0 `cache_scope` tenancy test | 3 | 1 | — (testability) | Prove typed-judgment isolation | Shipped [#1562](https://github.com/naveenreddyalka/daari/pull/1562) |
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

Shipped this week (do not re-file): rows 60/61/64/68/69; keys export/import
round-trip (`last_used_at`, `priority`, `cache_scope`); virtual_keys lifecycle
stats + Grafana panels + scrape test; key_expiry webhook signing-secret doctor
tip; keys list `--status`/`--idle-days` CLI + docs; doctor-health key_expiry
docs; rows 53–59 from the 10-09/10-10 tables (decisions governance, Ultrafast,
haiku fidelity, lifecycle/server_tools, pooled revoked-jti).

Watch rows (do not file yet): opt-in **fail-closed rate-limit mode** (LiteLLM
1.105 GA parity; daari's SQLite-fallback default keeps limits enforced
per-replica, which is arguably better — file if a regulated buyer wants strict
503); **request-log shared backend** (JSONL-only, last per-pod store; every
other store has a Redis/Postgres option); **Prometheus exemplars +
shipped PrometheusRule alerts + `/mcp/proxy` Prom request metrics**;
**`gen_ai.agent.*` semconv spans** (conversation.id already emitted); **SCIM +
multi-issuer/audience SSO** (group→team mapping + multi-JWKS exist; file on
identity-buyer ask); **per-user request-count RPD** (USD caps exist);
compare-litellm refresh for 1.105 GA (open docs issue covers the Decisions
note); team-member budget percentage alerts; gpt-6-luna Decisions schema
drift; OpenRouter BYOK `declared_region` + enterprise IP allowlists; Anthropic
Managed Agents / Compliance API chat export (non-goals); Claude Max/Team
monthly API credits; Portkey v2.28.0 JWT JIT access; OpenAI in-product HIPAA
BAA (compliance non-goal); OpenAI Agents API harness (platform-side).

Verified fine this run — don't re-audit: team aggregate RPM/TPM/RPD + key RPD
+ admission priority classes (high/normal/low); Redis/Postgres options for
keys, teams, audit, responses, batches, files, spend, usage, idempotency,
traces, revoked-JTI, session pins, L0/L1 caches, rate-limit counters; Helm
PDB + ServiceMonitor + securityContext/readOnlyRootFilesystem + rolling
strategy/preStop (defaults off where noted); decisions/OCR/systemone all have
Prom metrics + OTel spans; `gen_ai.conversation.id` + cache-token semconv
emitted; SSO `groups`→team/key mapping + multi-JWKS; SSO bearers blocked from
inference; rate-limit Redis degradation falls back to SQLite with `/ready`
exposure.

---

## Path to enterprise-grade — next 5 milestones

1. **Close the admin-plane RBAC holes** — role floors on `route/preview`,
   `cache/diversity`, `learn/stats`, `feedback` (row 70); feedback poisoning
   is the sharpest open governance gap.
2. **Decisions-ecosystem agility** — local decision-model guardrail judge
   (row 71) and a configurable judge catalog incl. Drex 1.5 /
   Microsoft-Decision-1 (row 72): the open-weight judge wave is daari's
   home turf.
3. **Quota depth for local fleets** — per-key max in-flight + named per-model
   rate/concurrency map (row 74) so one agent key cannot starve a GPU tier.
4. **Chart security baseline** — NetworkPolicy + topology spread (row 73) to
   pass platform reviews stock.
5. **Drain the in-flight admin/FinOps rows** — end-user registry (62),
   guardrail profiles (63), web-ui pagination (65), bounded rollups (66),
   multi_agent pricing (67); then hot-reload (6) and the parked Messages
   tool allowlist (7) when a long session is available.

Compliance non-goals (WIF depth, A2A, SOC 2 program, Realtime/WS, FIPS
builds, HIPAA BAA) stay deferred until buyer demand.

---

## Changelog

- **2026-10-11 (RBAC honesty + decisions agility + fleet-chart depth)** —
  Rows 60/61/64/68/69 marked Shipped (<24h drain again). Filed rows 70–74:
  ungated `/v1/daari` role floors (feedback poisoning P1), local
  decision-model guardrail, configurable decisions catalog with Drex 1.5 /
  Microsoft-Decision-1, Helm NetworkPolicy + spread knobs, per-key/per-model
  quota depth. Outward: LiteLLM v1.105.0 STABLE (fail-closed rate limiting,
  guardrail exec bounds, Lens GA; 1.106-rc backports decision-model guardrail
  + Microsoft-Decision-1); open-weight decision models (Drex 1.5,
  Microsoft-Decision-1) arrive; Ollama 0.40.3 trivial; rest flat. New watch
  rows: fail-closed RL mode, request-log shared backend, Prom exemplars/rules,
  `gen_ai.agent.*`, SCIM/multi-issuer, user RPD.

- **2026-10-10 eve (admin-plane honesty + FinOps + catalog ACL)** — Filed
  rows 65–69: web-ui pagination/`users`, bounded report rollups, multi_agent
  per-subagent model pricing, decisions L0 cache_scope hermetic test, filtered
  `/v1/models` catalog. Outward: LiteLLM 1.105 still RC; OpenRouter
  filtered-catalog parity; gateways otherwise flat.

- **2026-10-10 pm (key + end-user lifecycle governance)** — Row 53 marked
  Shipped (same-day drain). Filed rows 60–64 after a code audit of key/user
  lifecycle. Outward: OpenRouter Oct 6–9 admin-plane wave.

- **2026-10-10 (Oct 7–10 drain: mark shipped, re-aim path)** — Rows 55–59
  marked Shipped with PR links; stand/path rewritten for current `main`.

- **2026-10-09 → 08-28** — Condensed: governance parity + billing truth
  (Ultrafast, haiku 400, luna); depth on Decisions/OAuth/admin/multi-agent;
  catalog + classifier; LiteLLM 1.104; OBO/classifier; MCP OAuth; Apache 2.0;
  this PRD's creation.
