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

**Loop velocity.** The 10-09 governance/billing table (rows 55–59) drained the
same day: decisions model/user 402s + `user_id` ledger, Ultrafast 6× with
model/EU gating, haiku-5-5 `budget_tokens` compat + 5m write rate, OpenAI-shape
lifecycle/`server_tools` with fail-closed retirement, and pooled Postgres
revoked-jti lookups. Follow-on drain added decisions L0 cache, `chat-latest`
catalog alias, Fast=`priority` 2×, Idempotency-Key + stream reject-400 on
`/v1/decisions`, audit list pagination, and OpenAI regional-processing 1.10×
when `region_pin` is us/eu. Only the ops-docs row (53) and long-running
hot-reload / Messages tool-allowlist rows stay open.

**Outward.** OpenAI Ultrafast + Fast rename and regional-processing uplift are
now billed honestly in-tree. Anthropic Haiku 5.5 breaking-change absorption
landed. LiteLLM stable bar stays **v1.104.2** (1.105/1.106 still RC/dev).
Portkey **v2.28.0**, Kong **2.2.0**, vLLM 0.31.0, OpenRouter / MCP blog flat.
Ollama **0.40.2** (background upgrades — runtime-only).

**Inward theme: operate honesty and config ownership.** Code audit (10-10)
confirmed: doctor/Helm/auth-and-keys still under-document `/v1/decisions`;
`Settings` still requires process restart for `config.yaml` edits; Messages
`mcp_servers` still lack a per-key tool-name allowlist subset. Admin
`/v1/daari/audit` pagination shipped — remaining watch is web-ui `has_more`
and unbounded report rollups.

---

## Scored gap table

| # | Gap | Impact | Effort | Who does it best today | Why daari wins local-first | Action |
|---|-----|:--:|:--:|------------------------|----------------------------|--------|
| 53 | Doctor + Helm + auth-and-keys coverage for `/v1/decisions` | 3 | 1 | — (ops honesty) | Operators discover the surface | Filed [#1501](https://github.com/naveenreddyalka/daari/issues/1501) |
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

Watch rows (do not file yet): web-ui ignores admin `has_more`;
`/v1/daari/report` clients/users unbounded (file at fleet-scale ask);
multi_agent per-subagent-model pricing (`nested_agent_usages` has no `model`);
gpt-6-luna Decisions schema drift while the beta hardens; Anthropic Compliance
API chat export (org-level, non-goal); Anthropic SDK browser/computer-use
toolsets (client-side); Claude Max/Team monthly API credits; LiteLLM
1.105/1.106 M365 MCP catalog + scoped-SQL tracing (file at GA); Portkey
v2.28.0 JWT JIT access (operator ask); OpenAI in-product HIPAA BAA
(compliance non-goal).

Verified fine this run — don't re-audit: decisions rate family + cost headers
+ pooled httpx + spend-context user binding + budget 402s; Ultrafast/Fast
tier factors + EU astra gate; regional-processing factor; haiku threshold
scaling; OpenAI + Anthropic `/v1/models` lifecycle filter + server_tools;
revoked-jti doctor + pooled Postgres path; multi_agent double-bill guard;
audit/keys/teams list pagination.

---

## Path to enterprise-grade — next 5 milestones

1. **Operate honesty for Decisions** — doctor + Helm + auth-and-keys coverage
   for `/v1/decisions` (row 53) so fleets discover the surface without reading
   the changelog.
2. **Config ownership without restart** — hot-reload `Settings` from
   `config.yaml` (row 6) so residency/budget/provider edits take effect
   mid-flight.
3. **MCP tool allowlist depth** — per-key tool-name subset for Messages
   `mcp_servers` (row 7), parked until a ≥60m session can land it safely.
4. **Admin plane at fleet scale** — web-ui `has_more` + bounded report
   rollups (watch) once an operator hits the current caps.
5. **Multi-model agent FinOps** — per-subagent-model pricing on nested usages
   (watch) when multi-model agent graphs leave the lab.

Compliance non-goals (WIF depth, A2A, SOC 2 program, Realtime/WS, FIPS
builds, HIPAA BAA) stay deferred until buyer demand.

---

## Changelog

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
