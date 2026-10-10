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

**Loop velocity.** Key/user lifecycle feeder (rows 60–64) still open from the
pm scan; hot-reload (6) and parked Messages tool-allowlist (7) unchanged.
This eve run does not wait on that drain — never-empty contract: file the next
admin-plane / FinOps / catalog gaps now.

**Outward.** Gateways still flat at stable bars: LiteLLM **v1.104.2** (1.105
at rc.3 with Lens/Agent Traces + `litellm.agent()` — file compare refresh at
GA; 1.106 still dev), Portkey **v2.28.0**, Kong **2.2.0**, vLLM **0.31.0**,
Ollama **0.40.2**. OpenRouter admin-plane wave (keys `last_used_at`, end-users,
guardrail→key assign) already drove rows 60–64; remaining OpenRouter parity is
**filtered model catalog** (`is_filtered_model_catalog_enabled`). LiteLLM RC
theme (agent traces + paged usage UIs) validates our report/web-ui bounds work.

**Inward theme: admin-plane honesty + FinOps depth + catalog ACL.** Code audit:
web-ui ignores `has_more` on keys/teams and never renders `report.users`;
report `clients`/`users` rollups are unbounded; `nested_agent_usages` omits
`model` so multi_agent subagents bill at parent price; decisions L0 has no
hermetic `cache_scope` tenancy test; `GET /v1/models` ignores VK allowlists.

---

## Scored gap table

| # | Gap | Impact | Effort | Who does it best today | Why daari wins local-first | Action |
|---|-----|:--:|:--:|------------------------|----------------------------|--------|
| 69 | Filter `GET /v1/models` by VK `allowed_models` | 5 | 2 | OpenRouter filtered catalog | Same allowlist as inference | Filed [#1555](https://github.com/naveenreddyalka/daari/issues/1555) |
| 65 | Web-ui: honor keys/teams `has_more` + render `report.users` | 4 | 2 | LiteLLM admin UI | Same-box console finishes the job | Filed [#1551](https://github.com/naveenreddyalka/daari/issues/1551) |
| 66 | Bound/paginate report `clients`/`users` rollups | 4 | 2 | LiteLLM paged usage | Fleet-safe JSON on-box | Filed [#1552](https://github.com/naveenreddyalka/daari/issues/1552) |
| 67 | multi_agent nested usage: per-subagent `model` for cost-true pricing | 4 | 2 | OpenAI / LiteLLM FinOps | Ledger already meters nested tokens | Filed [#1553](https://github.com/naveenreddyalka/daari/issues/1553) |
| 68 | Hermetic decisions L0 `cache_scope` tenancy test | 3 | 1 | — (testability) | Prove typed-judgment isolation | Filed [#1554](https://github.com/naveenreddyalka/daari/issues/1554) |
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
| 8 | Full DCR; A2A; Realtime/WS; stdio MCP; M365 catalog; Skills; FIPS; HIPAA BAA | 2–4 | 3–5 | Portkey / Kong / LiteLLM / OpenAI | Demand-triggered | Watch |

Shipped this week (do not re-file): rows 55–59; decisions L0 cache;
`chat-latest` alias; Fast service_tier 2×; Idempotency-Key + stream reject on
decisions; audit `limit`/`offset` pagination; regional-processing 1.10× uplift;
haiku-5-5 catalog + cache-read reprice; gpt-6-luna cached-input + decisions
input-only; fleet revoked-jti; admin keys/teams pagination; multi_agent nested
metering; Anthropic + OpenAI lifecycle/`server_tools`; ops-docs for decisions.

Watch rows (do not file yet): gpt-6-luna Decisions schema drift while the beta
hardens; OpenRouter BYOK `declared_region` (daari `region_pin` covers routing;
file only if clients want declared-region metadata on stored provider keys);
OpenRouter enterprise IP allowlists (file at buyer ask); Anthropic Managed
Agents dynamic workflows (platform-side, non-goal); Anthropic Compliance API
chat export (org-level, non-goal); Claude Max/Team monthly API credits;
LiteLLM 1.105/1.106 Lens + agent traces + M365 MCP catalog (file compare +
scoped features at GA); Portkey v2.28.0 JWT JIT access (operator ask); OpenAI
in-product HIPAA BAA (compliance non-goal).

Verified fine this run — don't re-audit: regional-processing 1.10× wired into
cost headers, stream usage, spend ledger, and decisions billing; decisions L0
honors `X-Daari-No-Cache` + builds tenancy-scoped keys via
`apply_auth_claims_to_meta` (hermetic cross-key miss still missing — row 68);
retired-model 410 enforcement on inference facades; key expiry enforcement +
rotation grace + SSO key TTL; end-user spend attribution (`--by-user`, report
`users`, key-level `user_daily_usd_cap` 402s); MCP per-key/team tool/server
governance; decisions rate family + budget 402s; Ultrafast/Fast tier factors;
audit/keys/teams list pagination (API done; UI follow-through is row 65).

---

## Path to enterprise-grade — next 5 milestones

1. **Catalog ACL honesty** — filter `/v1/models` by VK allowlist (row 69) so
   clients never advertise models the key will 403.
2. **Admin plane at fleet scale** — web-ui `has_more` + `report.users` (row 65)
   and bounded report rollups (row 66); finish what keys/teams pagination started.
3. **Credential + end-user lifecycle** — drain rows 60–62 (`last_used_at`,
   expiry signals, end-user registry/block/cap) from the pm feeder.
4. **Per-tenant policy + FinOps depth** — guardrail profiles (row 63),
   cost-true multi_agent models (row 67), retired-block observability (row 64).
5. **Operate without restart** — hermetic decisions tenancy proof (row 68),
   then config hot-reload (row 6) and parked Messages tool allowlist (row 7)
   when a long session is available.

Compliance non-goals (WIF depth, A2A, SOC 2 program, Realtime/WS, FIPS
builds, HIPAA BAA) stay deferred until buyer demand.

---

## Changelog

- **2026-10-10 eve (admin-plane honesty + FinOps + catalog ACL)** — Filed
  rows 65–69: web-ui pagination/`users`, bounded report rollups, multi_agent
  per-subagent model pricing, decisions L0 cache_scope hermetic test, filtered
  `/v1/models` catalog. Outward: LiteLLM 1.105 still RC (Lens/agent traces —
  watch for GA); OpenRouter filtered-catalog parity; gateways otherwise flat.
  Pruned condensed early shipped rows 19–28 / 45–48 from the table (still in
  git history); watch list drops the four gaps now filed.

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

- **2026-10-08 → 08-28** — Condensed: depth on Decisions/OAuth/admin/
  multi-agent; governance parity; catalog + classifier; LiteLLM 1.104;
  OBO/classifier; MCP OAuth; Apache 2.0; this PRD's creation.
