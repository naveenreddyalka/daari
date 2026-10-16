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

## Where daari stands (verified in-tree, 2026-10-16 evening)

**Loop velocity.** Morning board (rows 117–121) is filed and still open:
retired-410 on the remaining doors, Opus 5.5 fast mode, tenancy totals,
lockout unlock, Helm consistent backup. Rows 6/62–63/65–67 stay
`agent:working`. This run does not re-file them.

**Outward (evening re-scan).** No new stable GA past the morning note.
LiteLLM stable remains 1.105.1; **1.107.0-dev.3** (16 Oct) is still the
tip — gzip >16 KiB off the event loop, scoped `/spend/tags`, generic 401
for unknown keys, plus cosign-signed images, MiniMax-H3 video on
`/v1/videos`, and per-model budget-reset reporting. daari already exposes
`daari_team_budget_remaining_hours`; it still has **no response
compression**. Ollama holds at **0.40.5** (`clef:cloud` still meters as
$0 local). Portkey, Kong AI Gateway 2.2.0, vLLM 0.31.0, and OpenRouter
(changelog through Oct 9) are unchanged. Anthropic fast mode and GPT-Live
stay as filed / non-goal from the morning scan.

**Inward theme: defaults and honesty at the edges of what just shipped.**
`doctor --strict` still exits 0 on cleartext remote Postgres/Redis
(`optional=True`). `GET /v1/daari/events` does not write an audit row,
and keys/teams/audit lists cannot filter by `team_id`. There is no
`daari configure codex` even though Ollama 0.40.4 ships `ollama launch
codex`. JSON bodies are never gzipped.

---

## Scored gap table

| # | Gap | Impact | Effort | Who does it best today | Why daari wins local-first | Action |
|---|-----|:--:|:--:|------------------------|----------------------------|--------|
| 122 | Bill Ollama `:cloud` models (`clef:cloud`) instead of $0 local | 5 | 2 | Ollama account billing | On-box ledger matches the cloud hop | Filed [#1707](https://github.com/naveenreddyalka/daari/issues/1707) |
| 123 | `doctor --strict` fails cleartext remote PG/Redis and http egress | 4 | 2 | Managed gateways "TLS required" | Air-gapped fail-the-deploy, no policy SaaS | Filed [#1708](https://github.com/naveenreddyalka/daari/issues/1708) |
| 124 | `daari configure codex` print-only recipe | 3 | 2 | `ollama launch codex` | Cache and budgets sit on 127.0.0.1 beside the CLI | Filed [#1709](https://github.com/naveenreddyalka/daari/issues/1709) |
| 125 | Gzip JSON responses >16 KiB off the event loop | 3 | 2 | LiteLLM 1.107-dev.3 | Stdlib gzip, loop stays free for local inference | Filed [#1710](https://github.com/naveenreddyalka/daari/issues/1710) |
| 126 | Audit `admin.events.list`; `team_id` filter on keys/teams/audit | 4 | 2 | Portkey / LiteLLM admin | Hash-chained proof on the operator's store | Filed [#1711](https://github.com/naveenreddyalka/daari/issues/1711) |
| 117 | Retired-410 on modality/MCP/batch doors, before admission | 5 | 2 | OpenAI / LiteLLM uniform deny | Fail closed before GPU or slots | Filed |
| 118 | Anthropic Opus 5.5 fast mode: forward `speed`, bill 2× | 5 | 2 | Anthropic API direct | Cost-true ledger on fallback | Filed |
| 119 | Tenancy leaks: trace detail, report totals, stats counters | 5 | 3 | Portkey / LiteLLM team dashboards | Rows already carry team_id | Filed |
| 120 | Key-prefix lockout: unlock verb + doctor + alert webhook | 4 | 2 | OpenRouter Security Center | On-box unlock, one audited call | Filed |
| 121 | Consistent backup as the deployed Helm default | 4 | 2 | Managed Postgres PITR | Air-gapped app-consistent DR | Filed |
| 96 | compare-litellm: 1.105.0 GA framing vs multi_agent | 2 | 1 | LiteLLM release notes | Honest local-first positioning | Open |
| 62 | End-user inventory + per-user block/cap overrides | 5 | 3 | OpenRouter / LiteLLM | Ledger already knows every user | Open |
| 63 | Named guardrail profiles bindable per key/team | 5 | 3 | OpenRouter / Portkey | Per-tenant policy, zero hops | Open |
| 65 | Web-ui: honor keys/teams `has_more` + render `report.users` | 4 | 2 | LiteLLM admin UI | Same-box console | Open |
| 66 | Bound/paginate report `clients`/`users` rollups | 4 | 2 | LiteLLM paged usage | Fleet-safe JSON on-box | Open |
| 67 | multi_agent nested usage: per-subagent `model` | 4 | 2 | OpenAI / LiteLLM FinOps | Ledger meters nested tokens | Open |
| 6 | Hot-reload `config.yaml` | 3 | 2 | LiteLLM config ownership | Open — long session | Open |
| 7 | Per-key tool-name allowlist for Messages `mcp_servers` | 4 | 3 | LiteLLM `mcp_tool_permissions` | Parked (≥60m session) | Parked |
| 107–116, 90/91/78, 19–28 | Lifecycle, tenancy lists, DR, TLS warn, webhooks, trace header, events HTTP, lockout, Grafana, chatgpt-desktop, compact-to-fit, MCP grant | — | — | — | Shipped this week | Shipped |
| 8 | Full DCR; A2A; Realtime/WS (incl. GPT-Live); stdio MCP; M365; Skills; FIPS; HIPAA BAA | 2–4 | 3–5 | Portkey / Kong / LiteLLM / OpenAI | Demand-triggered | Watch |

Shipped this week (do not re-file): retired-410 on the primary facades;
team_id scoping on traces/stats/report **lists**; `backup create
--consistent`; PG/Redis TLS **warn** checks; dual-secret webhook rotation;
member budget webhooks; W3C `traceresponse`; `GET /v1/daari/events`;
key-prefix lockout; Grafana errors-by-status; `daari configure
chatgpt-desktop`; DEC/SYS bench docs; team budget remaining-hours gauge.

Watch rows (do not file yet): runtime schema/version-skew (`/ready` has
no `schema_ok`; no `migrate --downgrade`); Responses background webhooks
and a wider `include` allowlist; per-user request-count RPD; SCIM and
multi-issuer SSO; Prometheus exemplars and `gen_ai.agent.*` spans;
Portkey JWT claims→metadata routing; LiteLLM 1.107 GA (cosign images,
MiniMax `/v1/videos` — video stays a non-goal until a buyer asks);
Anthropic Compliance API export; OpenAI GPT-Live (non-goal). Further
agent-CLI recipes (gemini-cli, opencode, cursor-cli) wait until `codex`
lands.

Verified fine this run — don't re-audit: events list is analyst-gated,
team-scoped, cursor-paginated (gap is the missing audit row); keys and
teams lists already audit; `/ready` reports cache, model backend, redis,
and postgres (gap is schema skew, left on watch); `pricing.models`
overrides unknown frontier models and doctor warns — `:cloud` ids do not
hit that path; ChatGPT Desktop recipe is print-only and registered.

---

## Path to enterprise-grade — next 5 milestones

1. **Finish the morning lifecycle board** — remaining-door 410s, team
   totals, fast-mode billing, lockout unlock, Helm backup default
   (rows 117–121).
2. **Cost-true local cloud hops** — Ollama `:cloud` models stop metering
   as $0 (row 122), beside the fast-mode bill in row 118.
3. **Strict day-2 defaults** — `doctor --strict` fails cleartext remote
   data planes and http egress (row 123).
4. **Admin-plane proof and client reach** — events-list audit and
   team filters (row 126); Codex configure recipe (row 124).
5. **Wire efficiency** — gzip large JSON off the event loop (row 125).
   Schema skew, Responses webhooks, and exemplars stay on watch.

Compliance non-goals (SCIM, WIF depth, A2A, SOC 2 program, Realtime/WS,
FIPS builds, HIPAA BAA, video generation) stay deferred until buyer demand.

---

## Changelog

- **2026-10-16 (evening: cloud billing, strict TLS, Codex, gzip, admin
  audit)** — Morning rows 117–121 left filed (not re-opened). Outward
  re-scan: LiteLLM still 1.107.0-dev.3 (gzip, cosign, MiniMax video);
  Ollama still 0.40.5; Portkey / Kong 2.2.0 / vLLM 0.31.0 / OpenRouter
  flat. Filed rows 122–126: price `:cloud` models, `doctor --strict`
  on cleartext remote PG/Redis and http egress, Codex configure recipe,
  gzip JSON >16 KiB off the event loop, audit `admin.events.list` plus
  `team_id` filters.

- **2026-10-16 (edge-depth scan)** — Filed rows 117–121 (lifecycle doors,
  fast mode, tenancy totals, lockout unlock, Helm backup). Shipped
  rows 107–116 and 90/91/78.

- **2026-10-15 → 08-28** — Condensed: post-wave lifecycle/tenancy/DR/TLS;
  overnight parity; day-2 ops; concurrency; export honesty; RBAC; Apache
  2.0; this PRD's creation.
