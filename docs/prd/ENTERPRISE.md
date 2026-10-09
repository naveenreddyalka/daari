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

## Where daari stands (verified in-tree, 2026-10-09)

**Loop velocity.** The whole 10-08 table (rows 49–52, 54) drained in under a
day: the queued Haiku 5.5 catalog + Sonnet/Opus cache-read reprice, gpt-6-luna
cached-input billing, decisions guardrails/OTel/retry + alias normalization,
the fleet-durable OAuth revoked-jti denylist, admin keys/teams pagination +
audit, multi_agent subagent metering, and Anthropic `server_tools` + lifecycle
on native `/v1/models`. Only the ops-docs row (53) stays open, alongside the
decisions L0 cache and chat-latest alias refills.

**Outward.** **OpenAI shipped Ultrafast mode** — `service_tier: "ultrafast"`
on the Responses API for `gpt-6.1-sol` (8 Oct, US+EU residency) and
`gpt-6-astra` (29 Sep, US only) with dedicated pricing; daari's tier table
doesn't know it, so ultrafast traffic bills at 1.0× today. **Anthropic's
Haiku 5.5 is a breaking change**: manual `budget_tokens` thinking now 400s
and adaptive thinking defaults on — daari forwards client thinking verbatim
on Anthropic egress, so migrating clients break through daari too. Anthropic
also added Compliance API chat endpoints for unified Claude chats (8 Oct,
org-level — non-goal). LiteLLM stable bar stays **v1.104.2** (10-08 backport
patches v1.102.4/v1.101.6 are maintenance; 1.105-rc.3/1.106-dev.2 carry the
known decisions backports). Portkey **v2.28.0**, Kong **2.2.0**, vLLM 0.31.0,
OpenRouter (08-19), MCP blog (08-22) all flat. **Ollama 0.40.2 stable**
(background model upgrades + backups — runtime-only, facade unaffected).

**Inward theme: governance parity and billing truth on the newest surfaces.**
Code audit (10-09) confirmed: `/v1/decisions` skips chat's per-model /
per-user 402 pre-checks and drops `user_id` from the usage ledger; the
OpenAI-shaped `/v1/models` lacks the lifecycle + `server_tools` fields the
Anthropic shape just gained, and lifecycle is advertise-only (retired models
still route); the haiku-5-5 row under-bills 5m cache writes ($0.10 vs $0.125,
$0.50 vs $0.625 above 100K); the new Postgres revoked-jti denylist opens two
raw connections per MCP token validation despite the pooled-store work.

---

## Scored gap table

| # | Gap | Impact | Effort | Who does it best today | Why daari wins local-first | Action |
|---|-----|:--:|:--:|------------------------|----------------------------|--------|
| 55 | Model/user budget 402 pre-checks + `user_id` ledger rows on `/v1/decisions` | 5 | 2 | LiteLLM model budgets (chat only) | 402 a scoped key before any call; per-user chargeback on typed judgments | Filed [#1518](https://github.com/naveenreddyalka/daari/issues/1518) |
| 56 | Ultrafast service tier: true pricing + model/residency gating | 4 | 2 | OpenAI Ultrafast pricing page | Bill the premium tier honestly; refuse EU-pinned astra ultrafast on-box | Filed [#1519](https://github.com/naveenreddyalka/daari/issues/1519) |
| 57 | claude-haiku-5-5 fidelity: budget_tokens→400 compat, 5m cache-write rate, cards | 4 | 2 | Anthropic migration guide; LiteLLM day-one catalogs | Absorb the provider breaking change for every client behind the gateway | Filed [#1520](https://github.com/naveenreddyalka/daari/issues/1520) |
| 58 | Lifecycle + server_tools on OpenAI-shaped `/v1/models`; fail-closed retired routing | 4 | 2 | Anthropic Models API | One catalog, two facades, enforced retirement | Filed [#1521](https://github.com/naveenreddyalka/daari/issues/1521) |
| 59 | Pooled connections for the Postgres revoked-jti denylist hot path | 4 | 2 | Kong Token Vault (pooled stores) | Fleet revoke stays cheap on the per-request auth path | Filed [#1522](https://github.com/naveenreddyalka/daari/issues/1522) |
| 53 | Doctor + Helm + auth-and-keys coverage for `/v1/decisions` | 3 | 1 | — (ops honesty) | Operators discover the surface | Filed [#1501](https://github.com/naveenreddyalka/daari/issues/1501) |
| 54 | claude-haiku-5-5 catalog + sonnet/opus-5-5 cache-read reprice | 5 | 1 | Anthropic pricing page | Cost-true routing on the new cheap tier | Shipped |
| 49 | Guardrails + OTel + retry + `user` spend on `/v1/decisions` | 5 | 2 | Portkey/Kong decisions policy | Same on-box policy engine as systemone/OCR | Shipped |
| 50 | Fleet-durable MCP OAuth revoked-jti denylist | 5 | 3 | Kong Token Vault | Revoke sticks across Helm replicas | Shipped |
| 51 | Paginate + audit `GET /v1/daari/keys` and `/teams` | 4 | 2 | LiteLLM admin UI | Control-plane honesty at key-store scale | Shipped |
| 52 | Meter multi_agent subagent token usage / spend on L6 | 4 | 2 | OpenAI aggregated usage | FinOps chargeback for delegated agents | Shipped |
| 44 | OpenAI-compatible `/v1/decisions` + gpt-6-luna | 5 | 2 | OpenAI Decisions beta; LiteLLM v1.104.2 | Typed judgments on-box | Shipped |
| 45 | MCP OAuth scope + RFC 7009 revocation | 4 | 2 | LiteLLM / Kong | On-box revoke/scope | Shipped |
| 46 | OTel + guardrails + retry on `/mcp/proxy` + `/v1/systemone` | 4 | 2 | Kong / Portkey | Local policy latency | Shipped |
| 47 | Web-ui read-only keys/teams/spend admin plane | 4 | 3 | LiteLLM admin UI | Same-box console | Shipped |
| 48 | Responses multi-agent forward or honest 400 | 3 | 2 | OpenAI multi-agent beta | Transparent L6 delegation | Shipped |
| 6 | Hot-reload `config.yaml` | 3 | 2 | LiteLLM config ownership | Open — in flight | Open |
| 7 | Per-key tool-name allowlist for Messages `mcp_servers` | 4 | 3 | LiteLLM `mcp_tool_permissions` | Parked (needs ≥60m session) | Parked |
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

Shipped this week (do not re-file): haiku-5-5 pricing row + sonnet/opus-5-5
cache-read reprice; gpt-6-luna cached-input $0.01 + decisions input-only
billing; decisions guardrails/OTel/retry + alias normalization; fleet-durable
revoked-jti denylist (Redis/Postgres/in-process + doctor); admin keys/teams
pagination + audit; multi_agent nested-usage metering; Anthropic
`server_tools` + lifecycle on native `/v1/models`; grok-4.7 /
claude-opus-5-5 catalog entries.

Watch rows (do not file yet): admin pagination depth — web-ui ignores
`has_more`, `GET /v1/daari/audit` hard-codes limit=100 with no offset,
`/v1/daari/report` clients/users unbounded (file when a fleet-scale operator
asks); multi_agent per-subagent-model pricing — `nested_agent_usages` keeps
no `model`, so absent provider cost all tokens bill at the parent model's
rate (file on multi-model agent-graph demand); decisions streaming reject-400
+ Idempotency-Key parity; decisions L0 cache + chat-latest alias (open
refills); gpt-6-luna Decisions schema drift while the beta hardens; Anthropic
Compliance API chat export (org-level, non-goal); Anthropic SDK
browser/computer-use toolsets (client-side loop); Claude Max/Team monthly API
credits (billing-side); LiteLLM 1.105/1.106 M365 MCP catalog + scoped-SQL
tracing (file at GA); Portkey v2.28.0 JWT just-in-time access (operator ask);
OpenAI in-product HIPAA BAA (compliance non-goal).

Verified fine this run — don't re-audit: decisions rate family + cost headers
+ pooled httpx + spend-context user binding; haiku threshold scaling for
input/output/cache-read/1h-write (boundary-tested at 100K); Anthropic-shaped
`/v1/models` lifecycle filter + server_tools; revoked-jti doctor coverage +
TTL prune + intentional omission from the backup catalog (TTL-bound);
multi_agent double-bill guard; admin keys/teams list audit events.

---

## Path to enterprise-grade — next 5 milestones

1. **Decisions governance parity** — model/user budget 402 pre-checks and
   per-user ledger attribution on `/v1/decisions` (row 55): the typed-judgment
   modality must meter and fence like chat before fleets adopt it at volume.
2. **Billing truth on the new provider tiers** — Ultrafast service-tier
   pricing with model + residency gating (row 56) and the haiku-5-5 5m
   cache-write rate (row 57): both are live billing-correctness defects.
3. **Breaking-change absorption** — haiku-5-5 `budget_tokens` → adaptive
   mapping on Anthropic egress (row 57) so clients migrate by doing nothing.
4. **Catalog honesty with teeth** — lifecycle + server_tools on the OpenAI
   shape and fail-closed retired routing (row 58).
5. **Auth hot-path efficiency** — pooled revoked-jti lookups (row 59), then
   the ops-docs row (53), hot-reload (row 6), and the parked Messages tool
   allowlist (row 7).

Compliance non-goals (WIF depth, A2A, SOC 2 program, Realtime/WS, FIPS
builds, HIPAA BAA) stay deferred until buyer demand.

---

## Changelog

- **2026-10-09 (governance parity + billing truth on newest surfaces)** —
  Rows 49–52 and 54 marked Shipped (drained in under a day, including the
  queued Haiku 5.5 reprice). Inward audit filed rows 55–59: decisions budget
  402s + user ledger, Ultrafast tier pricing/gating, haiku-5-5 fidelity
  (budget_tokens compat, 5m write rate, cards), OpenAI-shape lifecycle parity
  with fail-closed retirement, pooled revoked-jti lookups. Outward: OpenAI
  Ultrafast mode (sol 10-08, astra 09-29); Anthropic haiku `budget_tokens`
  400 breaking change + Compliance chat export; Ollama 0.40.2 stable;
  LiteLLM/Portkey/Kong/vLLM/OpenRouter/MCP flat.

- **2026-10-08 (depth on shipped Decisions / OAuth / admin / multi-agent)** —
  Filed rows 49–53 after the 10-07 table drained in a day; queued the Haiku
  5.5 catalog + cache-read reprice as row 54. LiteLLM v1.104.2 backported
  decisions/systemone to stable; Portkey v2.28.0.

- **2026-10-07 → 08-28** — Condensed: decisions surface + lifecycle depth;
  catalog + classifier/watchdog; admin-plane + OCR governance; operate-gates
  + FinOps; LiteLLM 1.104; OBO/classifier; decision models + MCP OAuth;
  Apache 2.0; this PRD's creation.
