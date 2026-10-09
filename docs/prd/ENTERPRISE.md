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

## Where daari stands (verified in-tree, 2026-10-09 pm)

**Loop velocity.** Same-day drain after the morning scan: decisions budget 402s
+ `user_id` ledger, decisions L0 exact cache, and the `chat-latest` rolling
alias all merged. Open from the morning table: Ultrafast tier pricing/gating,
haiku-5-5 fidelity, OpenAI-shape lifecycle + fail-closed retirement, pooled
revoked-jti, and the ops-docs row for `/v1/decisions`. Hot-reload stays in
flight; Messages tool allowlist stays parked.

**Outward.** OpenAI **Fast mode** (Priority rename, 30 Jul) is now the
documented client name — `service_tier: "fast"` ≡ `"priority"` at 2×; daari
only knows `priority`, so `fast` traffic under-bills at 1.0× today. Ultrafast
still live for `gpt-6.1-sol` / `gpt-6-astra` (morning row). Regional
processing adds a **10% uplift** on models released on/after 5 Mar 2026
(pricing page + Decisions guide); daari routes `region_pin` but does not
multiply spend. LiteLLM stable bar stays **v1.104.2**; 1.105-rc.3 / 1.106-dev.2
still pre-release. Portkey **v2.28.0**, Kong **2.2.0**, vLLM **0.31.0**,
Ollama **0.40.2**, OpenRouter/MCP blog flat. Anthropic Haiku 5.5
`budget_tokens` break + Compliance chat export unchanged (morning row).

**Inward theme: billing synonyms, decisions client-contract, admin depth.**
Code audit (10-09 pm): `_SERVICE_TIER_FACTORS` lacks `fast`; `/v1/decisions`
skips `Idempotency-Key` and silently ignores `stream: true` via
`extra="ignore"`; `GET /v1/daari/audit` hard-codes `limit=100` with no
offset/`has_more` while keys/teams already paginate; region-pinned spend
omits the 10% residency premium.

---

## Scored gap table

| # | Gap | Impact | Effort | Who does it best today | Why daari wins local-first | Action |
|---|-----|:--:|:--:|------------------------|----------------------------|--------|
| 60 | Alias `service_tier: "fast"` → 2.0× (OpenAI Fast mode) | 4 | 1 | OpenAI Fast mode guide | Stop under-billing clients on the renamed tier | Filed [#1527](https://github.com/naveenreddyalka/daari/issues/1527) |
| 61 | `Idempotency-Key` on `POST /v1/decisions` | 4 | 2 | LiteLLM / OpenAI chat idempotency | Safe retries without double L6/local spend | Filed [#1528](https://github.com/naveenreddyalka/daari/issues/1528) |
| 62 | Honest 400 when `stream=true` on `/v1/decisions` | 3 | 1 | Responses multi_agent fail-closed | Clear client contract for a non-SSE modality | Filed [#1529](https://github.com/naveenreddyalka/daari/issues/1529) |
| 63 | Paginate `GET /v1/daari/audit` (limit/offset/`has_more`) | 3 | 1 | LiteLLM admin audit export | Same admin-plane page contract as keys/teams | Filed [#1530](https://github.com/naveenreddyalka/daari/issues/1530) |
| 64 | Regional-processing 10% uplift when `region_pin` set | 4 | 2 | OpenAI pricing / residency invoice | Budgets match regional invoice on-box | Filed [#1531](https://github.com/naveenreddyalka/daari/issues/1531) |
| 56 | Ultrafast service tier: true pricing + model/residency gating | 4 | 2 | OpenAI Ultrafast pricing page | Bill the premium tier honestly; refuse EU-pinned astra ultrafast on-box | Filed [#1519](https://github.com/naveenreddyalka/daari/issues/1519) |
| 57 | claude-haiku-5-5 fidelity: budget_tokens→400 compat, 5m cache-write rate, cards | 4 | 2 | Anthropic migration guide; LiteLLM day-one catalogs | Absorb the provider breaking change for every client behind the gateway | Filed [#1520](https://github.com/naveenreddyalka/daari/issues/1520) |
| 58 | Lifecycle + server_tools on OpenAI-shaped `/v1/models`; fail-closed retired routing | 4 | 2 | Anthropic Models API | One catalog, two facades, enforced retirement | Filed [#1521](https://github.com/naveenreddyalka/daari/issues/1521) |
| 59 | Pooled connections for the Postgres revoked-jti denylist hot path | 4 | 2 | Kong Token Vault (pooled stores) | Fleet revoke stays cheap on the per-request auth path | Filed [#1522](https://github.com/naveenreddyalka/daari/issues/1522) |
| 53 | Doctor + Helm + auth-and-keys coverage for `/v1/decisions` | 3 | 1 | — (ops honesty) | Operators discover the surface | Filed [#1501](https://github.com/naveenreddyalka/daari/issues/1501) |
| 55 | Model/user budget 402 pre-checks + `user_id` ledger on `/v1/decisions` | 5 | 2 | LiteLLM model budgets | 402 before any call; per-user chargeback | Shipped |
| 54 | claude-haiku-5-5 catalog + sonnet/opus-5-5 cache-read reprice | 5 | 1 | Anthropic pricing page | Cost-true routing on the new cheap tier | Shipped |
| 49 | Guardrails + OTel + retry + `user` spend on `/v1/decisions` | 5 | 2 | Portkey/Kong decisions policy | Same on-box policy engine as systemone/OCR | Shipped |
| 50 | Fleet-durable MCP OAuth revoked-jti denylist | 5 | 3 | Kong Token Vault | Revoke sticks across Helm replicas | Shipped |
| 51 | Paginate + audit `GET /v1/daari/keys` and `/teams` | 4 | 2 | LiteLLM admin UI | Control-plane honesty at key-store scale | Shipped |
| 52 | Meter multi_agent subagent token usage / spend on L6 | 4 | 2 | OpenAI aggregated usage | FinOps chargeback for delegated agents | Shipped |
| 44 | OpenAI-compatible `/v1/decisions` + gpt-6-luna | 5 | 2 | OpenAI Decisions beta; LiteLLM v1.104.2 | Typed judgments on-box | Shipped |
| 6 | Hot-reload `config.yaml` | 3 | 2 | LiteLLM config ownership | Open — in flight | Open |
| 7 | Per-key tool-name allowlist for Messages `mcp_servers` | 4 | 3 | LiteLLM `mcp_tool_permissions` | Parked (needs ≥60m session) | Parked |
| 8 | Full DCR; A2A; Realtime/WS; stdio MCP; M365 catalog; Skills; FIPS; HIPAA BAA | 2–4 | 3–5 | Portkey / Kong / LiteLLM / OpenAI | Demand-triggered | Watch |

Shipped this week (do not re-file): haiku-5-5 pricing row + sonnet/opus-5-5
cache-read reprice; gpt-6-luna cached-input $0.01 + decisions input-only
billing; decisions guardrails/OTel/retry + alias normalization; fleet-durable
revoked-jti denylist; admin keys/teams pagination + audit; multi_agent
nested-usage metering; Anthropic `server_tools` + lifecycle on native
`/v1/models`; decisions budget 402s + `user_id` ledger; decisions L0 exact
cache; `chat-latest` rolling alias; grok-4.7 / claude-opus-5-5 catalog entries.

Watch rows (do not file yet): web-ui ignores `has_more` on keys/teams and
`/v1/daari/report` clients/users unbounded (file when a fleet-scale operator
asks — audit pagination filed first); multi_agent per-subagent-model pricing
(`nested_agent_usages` keeps no `model`); gpt-6-luna Decisions schema drift
while the beta hardens; Anthropic Compliance API chat export (org-level,
non-goal); Anthropic SDK browser/computer-use toolsets; Claude Max/Team
monthly API credits; LiteLLM 1.105/1.106 M365 MCP catalog + scoped-SQL
tracing (file at GA); Portkey v2.28.0 JWT just-in-time access; OpenAI
in-product HIPAA BAA; Kong Skills / Headroom (demand-triggered).

Verified fine this run — don't re-audit: decisions rate family + cost headers
+ pooled httpx + spend-context user binding + budget 402s + L0 cache;
haiku threshold scaling for input/output/cache-read/1h-write; Anthropic-shaped
`/v1/models` lifecycle filter + server_tools; revoked-jti doctor coverage +
TTL prune; multi_agent double-bill guard; admin keys/teams list audit events;
chat-latest alias mapping.

---

## Path to enterprise-grade — next 5 milestones

1. **Billing synonyms on renamed tiers** — `service_tier: "fast"` ≡ priority
   2.0× (row 60), then Ultrafast true rates + residency gating (row 56): stop
   live under-billing before fleets adopt Fast/Ultrafast via daari.
2. **Decisions client-contract parity** — Idempotency-Key replay (row 61) and
   honest `stream=true` 400 (row 62) so classifiers migrate without surprise
   double-spend or silent SSE drops.
3. **Regional invoice fidelity** — 10% uplift when `region_pin` is set
   (row 64) so residency-pinned spend matches OpenAI.
4. **Catalog honesty with teeth** — haiku-5-5 fidelity (row 57) and OpenAI-shape
   lifecycle + fail-closed retirement (row 58).
5. **Auth + admin depth** — pooled revoked-jti (row 59), audit pagination
   (row 63), ops-docs (row 53), then hot-reload (row 6) and the parked Messages
   tool allowlist (row 7).

Compliance non-goals (WIF depth, A2A, SOC 2 program, Realtime/WS, FIPS
builds, HIPAA BAA) stay deferred until buyer demand.

---

## Changelog

- **2026-10-09 pm (Fast-mode synonym + decisions contract + regional uplift)** —
  Morning rows 55 + decisions L0 + chat-latest marked Shipped. Filed rows
  60–64: `service_tier:"fast"` 2.0× alias, decisions Idempotency-Key, decisions
  stream reject-400, audit list pagination, regional 10% spend uplift. Outward:
  OpenAI Fast mode rename confirmed as client-facing name; regional 10% uplift
  on post-2026-03-05 models; LiteLLM/Portkey/Kong/vLLM/Ollama flat vs morning.

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
