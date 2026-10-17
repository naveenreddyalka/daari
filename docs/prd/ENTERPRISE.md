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

## Where daari stands (verified in-tree, 2026-10-16)

**Loop velocity.** The whole 10-15 board drained in under a day: rows 107–111
(retired-410 facades, team-scoped admin reads, consistent backup, TLS doctor,
webhook secret rotation) shipped as PRs #1688–#1693, the eve sibling's rows
112–116 (traceresponse, events HTTP, key lockout, Grafana errors-by-status,
chatgpt-desktop recipe) as #1689/#1694–#1697, and rows 90/91/78 (member
budget webhooks, DEC/SYS bench docs, LiteLLM 1.106 compare note) as
#1698–#1700. The dead eve PRD PR was drained to main again. Open:
compare row 96 and `agent:working` rows 6/62–63/65–67.

**Outward.** **Anthropic took Opus 5.5 fast mode GA (10-15)**: top-level
`speed: "fast"` on Messages, `usage.speed` in the reply, separate fast rate
limits, 2× pricing ($8/$40) — and Claude Code ships a `/fast` toggle, so a
flagship daari client now sends a field daari silently strips and would
misbill. **Ollama 0.40.5 stable (10-14)**: decision models on ollama.com
cloud (`clef:cloud`, `clef-flash:cloud`) and Nemotron 3.5 Super/Bolt — cloud
model usage through the facade would meter as $0 local. OpenAI added GPT-Live
native Decisions delegation (realtime stays a non-goal). LiteLLM stable holds
at 1.105.1; 1.107-dev.3 scopes `/spend/tags` to permitted teams, returns a
generic 401 for unknown keys, and gzips >16 KiB responses off the event loop
(daari has no response compression at all). Portkey v2.29.0, Kong 2.2.0,
vLLM 0.31.0, OpenRouter (Oct 9), MCP blog (Aug 22) flat.

**Inward theme: the shipped wave is real but thin at the edges.** Code audit
verified: the retired-410 gate covers eight doors but **not** images, speech,
transcriptions, moderations, rerank, MCP tools/call, or batch items — and
admission runs before the 410; team-scoped report/stats still return
fleet-wide totals and `GET /v1/daari/traces/{id}` is unscoped (any analyst
with a UUID reads any team's trace); the Helm backup CronJob never passes
`--consistent`, so K8s fleets keep taking the best-effort snapshot the
feature was built to replace; key-prefix lockout has no unlock verb —
recovery is TTL-or-restart.

---

## Scored gap table

| # | Gap | Impact | Effort | Who does it best today | Why daari wins local-first | Action |
|---|-----|:--:|:--:|------------------------|----------------------------|--------|
| 117 | Retired-410 on modality/MCP/batch doors, enforced before admission | 5 | 2 | OpenAI / LiteLLM uniform deny | Fail closed on every door before burning GPU or slots | Filed [#1701](https://github.com/naveenreddyalka/daari/issues/1701) |
| 118 | Anthropic Opus 5.5 fast mode: forward `speed`, bill 2× from `usage.speed` | 5 | 2 | Anthropic API direct | Cost-true ledger even when Anthropic falls back | Filed [#1702](https://github.com/naveenreddyalka/daari/issues/1702) |
| 119 | Tenancy leaks in scoped admin reads: trace detail, report totals, stats counters | 5 | 3 | Portkey / LiteLLM team dashboards | Rows carry team_id; isolation needs no SaaS plane | Filed [#1703](https://github.com/naveenreddyalka/daari/issues/1703) |
| 120 | Key-prefix lockout: unlock verb + doctor + alert webhook | 4 | 2 | OpenRouter Security Center | On-box unlock is one audited call, no WAF ticket | Filed [#1704](https://github.com/naveenreddyalka/daari/issues/1704) |
| 121 | Consistent backup as the deployed default (Helm flag, doctor, restore drill) | 4 | 2 | Managed Postgres PITR | Air-gapped app-consistent DR operators actually run | Filed [#1705](https://github.com/naveenreddyalka/daari/issues/1705) |
| 96 | compare-litellm: 1.105.0 GA framing + `litellm.agent()`/Lens vs multi_agent | 2 | 1 | LiteLLM release notes | Honest local-first positioning | Shipped |
| 62 | End-user inventory + per-user block/cap overrides | 5 | 3 | OpenRouter end-users / LiteLLM | Ledger already knows every user | Open |
| 63 | Named guardrail profiles bindable per key/team | 5 | 3 | OpenRouter / Portkey | Per-tenant policy, zero hops | Open |
| 65 | Web-ui: honor keys/teams `has_more` + render `report.users` | 4 | 2 | LiteLLM admin UI | Same-box console finishes the job | Open |
| 66 | Bound/paginate report `clients`/`users` rollups | 4 | 2 | LiteLLM paged usage | Fleet-safe JSON on-box | Open |
| 67 | multi_agent nested usage: per-subagent `model` for cost-true pricing | 4 | 2 | OpenAI / LiteLLM FinOps | Ledger already meters nested tokens | Open |
| 6 | Hot-reload `config.yaml` | 3 | 2 | LiteLLM config ownership | Open — needs long session | Open |
| 7 | Per-key tool-name allowlist for Messages `mcp_servers` | 4 | 3 | LiteLLM `mcp_tool_permissions` | Parked (needs ≥60m session) | Parked |
| 107–111 | 10-15 wave: retired-410 facades; team-scoped reads; consistent backup; TLS doctor; webhook secret rotation | 4–5 | 2–4 | — / Kong / Stripe-style | Lifecycle + tenancy + DR on-box | Shipped |
| 112–116 | 10-15 eve wave: traceresponse; events HTTP; key lockout; Grafana errors-by-status; chatgpt-desktop recipe | 3–5 | 1–3 | LiteLLM 1.107-dev | Trace round-trip + ops packaging on-box | Shipped |
| 90/91/78 | Member budget webhooks; DEC/SYS bench docs; LiteLLM 1.106 compare note | 2–3 | 1–3 | LiteLLM 1.105/1.106 | Runaway-agent alerts + benchmarking honesty | Shipped |
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
| 8 | Full DCR; A2A; Realtime/WS (incl. GPT-Live Decisions); stdio MCP; M365 catalog; Skills; FIPS; HIPAA BAA | 2–4 | 3–5 | Portkey / Kong / LiteLLM / OpenAI | Demand-triggered | Watch |

Shipped this week (do not re-file): retired-410 on chat/messages/Responses/
embeddings/decisions/OCR/systemone/Ollama facade; team_id scoping on
traces/stats/report **lists**; `backup create --consistent` CLI + docs;
PG/Redis TLS doctor warn checks; dual-secret webhook rotation incl. member
budget alerts; W3C `traceresponse` reply header; `GET /v1/daari/events`
(role-gated, team-scoped, paginated); key-prefix lockout (Redis-shared,
audited, Prom reject); Grafana errors-by-status panel; `daari configure
chatgpt-desktop`; per-member budget threshold webhooks; DEC/SYS bench docs.

Watch rows (do not file yet): admin-read polish — audit row on
`admin.events.list` + optional team filter on keys/teams/audit lists (fold
into the next tenancy slice after row 119); TLS enforcement — `doctor
--strict` fail on cleartext remote data planes + https checks on
webhook/OTLP/MCP egress URLs (shipped checks are warn-only, optional=True);
agent-CLI configure recipes: `codex` (Ollama 0.40.5 ships `ollama launch
codex`), gemini-cli, opencode, cursor-cli; Ollama cloud models
(`clef:cloud`) through facade/tiers meter as $0 local — price/flag them
when a fleet routes cloud-suffixed ids; gateway response compression
(gzip; LiteLLM just moved theirs off the event loop — daari has none);
runtime schema/version-skew guard: `/ready` has no `schema_ok`, no
`migrate --downgrade` (file on fleet-upgrade ask); Responses background
completion webhooks + wider `include` allowlist (one include today,
poll-only); per-user request-count RPD (USD caps only); SCIM + multi-issuer/
audience SSO (multi-JWKS yes, single issuer/audience str); Prometheus
exemplars + `gen_ai.agent.*` spans + PG request-log concurrency/soak tests;
Portkey v2.29 JWT claims→metadata conditional routing (buyer ask); LiteLLM
1.107 GA watchables; Anthropic Compliance API user-preferences export +
OpenAI GPT-Live (non-goals).

Verified fine this run — don't re-audit: retired-410 helper has audit +
Prom and runs before streaming on covered doors; `/v1/daari/events` is
analyst-gated, team-scoped, cursor-paginated (gap is the missing audit row);
member budget webhooks share the dual-secret signer and `rotate-secret
budget` path; key lockout shares state via Redis when `cache.backend=redis`;
`backup create --consistent` works and is documented (gap is deploy-path
defaults); PG/Redis TLS doctor checks exist as warn surfaces; Grafana
errors-by-status panel rendered; chatgpt-desktop registered in the client
registry.

---

## Path to enterprise-grade — next 5 milestones

1. **Finish lifecycle + tenancy honestly** — retired-410 on the remaining
   doors before admission (row 117) and no fleet totals in team-scoped
   reads (row 119); then the admin-read polish watch row.
2. **Provider fidelity that bills true** — Opus 5.5 fast mode forward +
   2× `usage.speed` billing (row 118); Ollama cloud-model pricing stays
   on watch behind it.
3. **Day-2 ops that defaults safe** — consistent backup in the Helm
   CronJob + doctor (row 121), lockout unlock verb (row 120), then TLS
   enforcement from watch.
4. **Admin-plane depth** — end-user inventory, guardrail profiles, web-ui
   pagination, report bounds, multi_agent pricing (rows 62–67) as the
   `agent:working` sessions land.
5. **Trace-native + onboarding polish** — agent-CLI configure recipes
   (codex first), Responses webhooks, exemplars/agent spans (watch rows →
   file as sessions open).

Compliance non-goals (SCIM, WIF depth, A2A, SOC 2 program, Realtime/WS,
FIPS builds, HIPAA BAA) stay deferred until buyer demand.

---

## Changelog

- **2026-10-16 (edge-depth scan: lifecycle doors, tenancy totals, fast mode,
  deploy defaults)** — Marked rows 107–116 and 90/91/78 Shipped (PRs
  #1688–#1700 drained the whole 10-15 board in <24h; drained the dead eve
  sibling PRD PR to main). Filed rows 117–121: retired-410 on
  modality/MCP/batch doors pre-admission, Opus 5.5 fast-mode forward +
  cost-true 2× billing, tenancy leaks in scoped admin reads, key-lockout
  unlock verb + doctor + webhook, consistent backup as the deployed Helm
  default. Outward: Anthropic fast mode GA (10-15), Ollama 0.40.5 cloud
  decision models, LiteLLM 1.107-dev.3 scoped spend tags + gzip; Portkey/
  Kong/vLLM/OpenRouter/MCP flat.

- **2026-10-15 (post-wave depth: lifecycle, tenancy, DR, data-plane TLS)** —
  Filed rows 107–111; eve sibling filed 112–116; all shipped by 10-16.
  Outward: Anthropic OTel export beta, Portkey v2.29.0, LiteLLM 1.107-dev
  watchables.

- **2026-10-14 → 08-28** — Condensed: overnight-wave parity depth; day-2
  operations + observability packaging; concurrency + decision-guardrail
  depth; control-plane honesty + MCP server rpm; export honesty + doctor
  ACL; team DR + console lifecycle; RBAC floors + decisions agility;
  key/end-user lifecycle; admin-plane honesty; Decisions/OAuth/multi-agent;
  governance parity; LiteLLM 1.104; Apache 2.0; this PRD's creation.
