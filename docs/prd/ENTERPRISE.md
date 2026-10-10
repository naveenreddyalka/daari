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

## Where daari stands (verified in-tree, 2026-10-10)

**Loop velocity.** The whole 10-09 table (rows 55–59) plus follow-ons drained
in under a day; by 17:11 on 10-10 even the ops-docs row (53) shipped, leaving
only long-running hot-reload (6) and the parked Messages tool-allowlist (7)
open. Fresh feeder filed 10-10 pm: rows 60–64 (key/user lifecycle governance).

**Outward.** Gateways flat: LiteLLM stable bar **v1.104.2** (1.105/1.106 still
RC/dev; dev churn is the Rust core + MCP elicitation relay), Portkey
**v2.28.0**, Kong **2.2.0**, vLLM 0.31.0, Ollama **0.40.2**, MCP blog 08-22.
The mover is **OpenRouter's Oct 6–9 admin-plane wave**: `last_used_at` +
`include_expired` on keys, an end-user CRUD API, guardrail objects with bulk
key assignment, and BYOK `declared_region`. Provider side quiet after 10-08
(Ultrafast on sol US+EU; Anthropic Managed Agents dynamic workflows are
platform-side, non-goal).

**Inward theme: key and end-user lifecycle governance.** Code audit (10-10 pm)
verified: virtual keys have no `last_used_at` and no status/idle list filters;
key expiry is reactive-401 only (no doctor scan, no Prometheus gauge, no
webhook); end-users are ledger dimensions with no registry, per-user cap
override, or cross-key block; chat guardrails are global-only while MCP tool
governance already resolves global → team → key; retired-model 410s are
log-only (no audit row/metric) and doctor never lifecycle-checks configured
tier/frontier models.

---

## Scored gap table

| # | Gap | Impact | Effort | Who does it best today | Why daari wins local-first | Action |
|---|-----|:--:|:--:|------------------------|----------------------------|--------|
| 60 | `last_used_at` on virtual keys + status/idle list filters | 4 | 2 | OpenRouter keys API | Key hygiene on-box, air-gapped | Filed [#1545](https://github.com/naveenreddyalka/daari/issues/1545) |
| 61 | Proactive key-expiry signals: doctor scan, Prom gauge, signed webhook | 4 | 2 | OpenRouter / LiteLLM alerts | Same store that enforces warns | Filed [#1546](https://github.com/naveenreddyalka/daari/issues/1546) |
| 62 | End-user inventory + per-user block/cap overrides | 5 | 3 | OpenRouter end-users / LiteLLM | Ledger already knows every user | Filed [#1547](https://github.com/naveenreddyalka/daari/issues/1547) |
| 63 | Named guardrail profiles bindable per key/team | 5 | 3 | OpenRouter guardrail assign / Portkey | Per-tenant policy, zero hops | Filed [#1548](https://github.com/naveenreddyalka/daari/issues/1548) |
| 64 | Audit + metric on retired-model blocks; doctor lifecycle check | 3 | 2 | LiteLLM audit planes | Catalog + router + audit in one box | Filed [#1549](https://github.com/naveenreddyalka/daari/issues/1549) |
| 53 | Doctor + Helm + auth-and-keys coverage for `/v1/decisions` | 3 | 1 | — (ops honesty) | Operators discover the surface | Shipped [#1544](https://github.com/naveenreddyalka/daari/pull/1544) |
| 6 | Hot-reload `config.yaml` | 3 | 2 | LiteLLM config ownership | Open — needs long session | Open [#1234](https://github.com/naveenreddyalka/daari/issues/1234) |
| 7 | Per-key tool-name allowlist for Messages `mcp_servers` | 4 | 3 | LiteLLM `mcp_tool_permissions` | Parked (needs ≥60m session) | Parked [#1288](https://github.com/naveenreddyalka/daari/issues/1288) |
| 55 | Model/user budget 402 pre-checks + `user_id` ledger on `/v1/decisions` | 5 | 2 | LiteLLM model budgets | Typed judgments meter like chat | Shipped [#1524](https://github.com/naveenreddyalka/daari/pull/1524) |
| 56 | Ultrafast service tier: true pricing + model/residency gating | 4 | 2 | OpenAI Ultrafast pricing | Bill premium tier honestly on-box | Shipped [#1535](https://github.com/naveenreddyalka/daari/pull/1535) |
| 57 | claude-haiku-5-5 fidelity: budget_tokens→400, 5m write, cards | 4 | 2 | Anthropic migration guide | Absorb provider breaking change | Shipped [#1536](https://github.com/naveenreddyalka/daari/pull/1536) |
| 58 | Lifecycle + server_tools on OpenAI `/v1/models`; fail-closed retirement | 4 | 2 | Anthropic Models API | One catalog, two facades | Shipped [#1537](https://github.com/naveenreddyalka/daari/pull/1537) |
| 59 | Pooled connections for Postgres revoked-jti denylist | 4 | 2 | Kong Token Vault | Fleet revoke stays cheap | Shipped [#1538](https://github.com/naveenreddyalka/daari/pull/1538) |
| 54 | claude-haiku-5-5 catalog + sonnet/opus-5-5 cache-read reprice | 5 | 1 | Anthropic pricing page | Cost-true routing | Shipped |
| 49 | Guardrails + OTel + retry + `user` spend on `/v1/decisions` | 5 | 2 | Portkey/Kong decisions policy | Same on-box policy engine | Shipped |
| 50 | Fleet-durable MCP OAuth revoked-jti denylist | 5 | 3 | Kong Token Vault | Revoke sticks across replicas | Shipped |
| 51 | Paginate + audit `GET /v1/daari/keys` and `/teams` | 4 | 2 | LiteLLM admin UI | Control-plane honesty | Shipped |
| 52 | Meter multi_agent subagent token usage / spend on L6 | 4 | 2 | OpenAI aggregated usage | FinOps for delegated agents | Shipped |
| 44 | OpenAI-compatible `/v1/decisions` + gpt-6-luna | 5 | 2 | OpenAI Decisions beta | Typed judgments on-box | Shipped |
| 45 | MCP OAuth scope + RFC 7009 revocation | 4 | 2 | LiteLLM / Kong | On-box revoke/scope | Shipped |
| 46 | OTel + guardrails + retry on `/mcp/proxy` + `/v1/systemone` | 4 | 2 | Kong / Portkey | Local policy latency | Shipped |
| 47 | Web-ui read-only keys/teams/spend admin plane | 4 | 3 | LiteLLM admin UI | Same-box console | Shipped |
| 48 | Responses multi-agent forward or honest 400 | 3 | 2 | OpenAI multi-agent beta | Transparent L6 delegation | Shipped |
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

Shipped this week (do not re-file): rows 55–59; decisions L0 cache;
`chat-latest` alias; Fast service_tier 2×; Idempotency-Key + stream reject on
decisions; audit `limit`/`offset` pagination; regional-processing 1.10× uplift
for us/eu `region_pin` on post-2026-03-05 OpenAI models; haiku-5-5 catalog +
cache-read reprice; gpt-6-luna cached-input + decisions input-only; fleet
revoked-jti; admin keys/teams pagination; multi_agent nested metering;
Anthropic + OpenAI lifecycle/`server_tools`.

Watch rows (do not file yet): web-ui ignores admin `has_more` and never
renders report `users`; `/v1/daari/report` clients/users unbounded (file at
fleet-scale ask); multi_agent per-subagent-model pricing
(`nested_agent_usages` has no `model`); decisions L0 lacks a hermetic
`cache_scope` tenancy test (fold into next test audit); gpt-6-luna Decisions
schema drift while the beta hardens; OpenRouter BYOK `declared_region`
(daari `region_pin` covers routing; file only if clients want declared-region
metadata on stored provider keys); Anthropic Managed Agents dynamic workflows
(platform-side, non-goal); Anthropic Compliance API chat export (org-level,
non-goal); Claude Max/Team monthly API credits; LiteLLM 1.105/1.106 M365 MCP
catalog + scoped-SQL tracing (file at GA); Portkey v2.28.0 JWT JIT access
(operator ask); OpenAI in-product HIPAA BAA (compliance non-goal).

Verified fine this run — don't re-audit: regional-processing 1.10× wired into
cost headers, stream usage, spend ledger, and decisions billing with unit
coverage; decisions L0 honors `X-Daari-No-Cache` + builds tenancy-scoped keys
via `apply_auth_claims_to_meta`; retired-model 410 enforcement itself on all
inference facades + deprecated warning header; key expiry enforcement +
rotation grace + SSO key TTL; end-user spend attribution (`--by-user`, report
`users`, key-level `user_daily_usd_cap` 402s, `daari erase --user`); MCP
per-key/team tool/server governance (`resolve_policy` global → team → key);
decisions rate family + budget 402s; Ultrafast/Fast tier factors + EU astra
gate; audit/keys/teams list pagination.

---

## Path to enterprise-grade — next 5 milestones

1. **Credential lifecycle hygiene** — `last_used_at` + status/idle filters
   (row 60) and proactive expiry signals (row 61) so operators find dead keys
   before auditors or 401s do.
2. **End-user governance** — user inventory + per-user block/cap overrides
   (row 62): stop one user on a shared agent key without revoking the key.
3. **Per-tenant guardrails** — named profiles bound per key/team (row 63),
   reusing the MCP global → team → key precedence already in-tree.
4. **Lifecycle operate honesty** — audited, metered retired-model blocks +
   doctor lifecycle checks (row 64), then config ownership without restart
   (row 6, hot-reload).
5. **Admin plane at fleet scale** — web-ui `has_more` + report `users`
   rendering + bounded rollups (watch), and the parked Messages tool
   allowlist (row 7) when a long session is available.

Compliance non-goals (WIF depth, A2A, SOC 2 program, Realtime/WS, FIPS
builds, HIPAA BAA) stay deferred until buyer demand.

---

## Changelog

- **2026-10-10 pm (key + end-user lifecycle governance)** — Row 53 marked
  Shipped (same-day drain). Filed rows 60–64 after a code audit of key/user
  lifecycle: `last_used_at`, expiry signals, end-user registry, per-tenant
  guardrail profiles, retired-block observability. Outward: OpenRouter Oct
  6–9 admin-plane wave (end-user CRUD, guardrail→key assignment, key
  `last_used_at`); gateways otherwise flat.

- **2026-10-10 (Oct 7–10 drain: mark shipped, re-aim path)** — Rows 55–59
  marked Shipped with PR links. Stand/path rewritten for current `main`:
  ops-docs (53), hot-reload (6), Messages tool allowlist (7) are the open
  feeder; watch rows drop decisions streaming/idempotency/audit-offset (all
  shipped). Changelog keeps the file under ~300 lines.

- **2026-10-09 (governance parity + billing truth on newest surfaces)** —
  Rows 49–52 and 54 marked Shipped. Filed rows 55–59. Outward: OpenAI
  Ultrafast; Anthropic haiku `budget_tokens` 400; Ollama 0.40.2.

- **2026-10-08 (depth on shipped Decisions / OAuth / admin / multi-agent)** —
  Filed rows 49–53; queued Haiku 5.5 as row 54. LiteLLM v1.104.2; Portkey
  v2.28.0.

- **2026-10-07 → 08-28** — Condensed: decisions surface + lifecycle depth;
  catalog + classifier/watchdog; admin-plane + OCR governance; operate-gates
  + FinOps; LiteLLM 1.104; OBO/classifier; decision models + MCP OAuth;
  Apache 2.0; this PRD's creation.
