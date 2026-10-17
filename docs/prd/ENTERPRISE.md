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

## Where daari stands (verified in-tree, 2026-10-17)

**Loop velocity.** Rows 117–121 shipped the day they were filed (modality
410, Opus fast-mode billing, team-scoped reads, lockout unlock, Helm
`--consistent`). The same window shipped Ollama `:cloud` metering, doctor
`--strict` egress/TLS, Codex print-only configure, gzip JSON over 16 KiB,
admin events audit + team filters, and LiteLLM 1.105.0 GA compare. Still
open and `agent:working`: rows 6/62–63/65–67. Refill this run: OpenCode
configure, Gemini CLI protocol honesty, `/ready` status docs, `schema_ok`.

**Outward.** **Anthropic took Opus 5.5 fast mode GA (10-15)**: top-level
`speed: "fast"` on Messages, `usage.speed` in the reply, separate fast rate
limits, 2× pricing ($8/$40) — and Claude Code ships a `/fast` toggle, so a
flagship daari client now sends a field daari silently strips and would
misbill. **Ollama 0.40.5 stable (10-14)**: decision models on ollama.com
cloud (`clef:cloud`, `clef-flash:cloud`) and Nemotron 3.5 Super/Bolt — cloud
model usage through the facade would meter as $0 local. OpenAI added GPT-Live
native Decisions delegation (realtime stays a non-goal). LiteLLM stable holds
at 1.105.1 (1.105.0 is GA; compare page updated). 1.107-dev.3 scopes
`/spend/tags` to permitted teams and returns a generic 401 for unknown keys.
Portkey v2.29.0, Kong 2.2.0, vLLM 0.31.0, OpenRouter (Oct 9), MCP blog
(Aug 22) flat. OpenCode v2 documents `providers.*.settings.baseURL` for
OpenAI-compatible servers; Gemini CLI still speaks the native Gemini API
via `GOOGLE_GEMINI_BASE_URL`, which daari does not implement.

**Inward theme: the 10-16 edge gaps shipped; the next thin edges are
client recipes and upgrade skew.** Retired-410 covers modality/MCP/batch
doors before admission. Team-scoped admin reads no longer return other
teams' traces, report totals, or stats. Helm backups default to
`--consistent` when Postgres is configured. Lockout has an unlock verb.
`/ready` still has no `schema_ok`. OpenCode and Gemini CLI have no
configure recipe; Gemini must not be pointed at the daemon as if it spoke
the native API.

---

## Scored gap table

| # | Gap | Impact | Effort | Who does it best today | Why daari wins local-first | Action |
|---|-----|:--:|:--:|------------------------|----------------------------|--------|
| 122 | OpenCode print-only configure (`providers` + `/v1` base URL) | 3 | 1 | OpenCode v2 providers | On-box OpenAI-compatible client, no config write | Filed [#1724](https://github.com/naveenreddyalka/daari/issues/1724) |
| 125 | `/ready` `schema_ok` when a local SQLite store lags the binary | 4 | 3 | — | Upgrade skew visible on the box that owns the files | Filed [#1727](https://github.com/naveenreddyalka/daari/issues/1727) |
| 123 | Gemini CLI configure must not aim the native API at daari | 2 | 1 | Gemini CLI `GOOGLE_GEMINI_BASE_URL` | Honest protocol boundary | Filed [#1725](https://github.com/naveenreddyalka/daari/issues/1725) |
| 124 | One operator page for `GET /ready` statuses | 2 | 1 | — | Probe contract next to the daemon | Filed [#1726](https://github.com/naveenreddyalka/daari/issues/1726) |
| 117–121 | Modality 410; Opus fast billing; scoped admin reads; lockout unlock; Helm consistent backup | 4–5 | 2–3 | — | Lifecycle, tenancy, DR on-box | Shipped |
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

Watch rows (do not file yet): cursor-agent CLI configure (distinct from
the Cursor IDE recipe); `migrate --downgrade` (schema_ok is filed; a
downgrade command stays demand-triggered); Responses background
completion webhooks + wider `include` allowlist (one include today,
poll-only); per-user request-count RPD (USD caps only); SCIM + multi-issuer/
audience SSO (multi-JWKS yes, single issuer/audience str); Prometheus
exemplars + `gen_ai.agent.*` spans + PG request-log concurrency/soak tests;
Portkey v2.29 JWT claims→metadata conditional routing (buyer ask); LiteLLM
1.107 GA watchables; Anthropic Compliance API user-preferences export +
OpenAI GPT-Live (non-goals).

Verified fine this run — don't re-audit: retired-410 on modality/MCP/batch
before admission; team-scoped traces/report/stats; lockout unlock; Helm
backup `--consistent` when Postgres is on; doctor `--strict` for remote
cleartext; gzip JSON over 16 KiB; Codex print-only configure; events list
audit row and team filters on keys/teams/audit; LiteLLM 1.105.0 marked GA
in compare-litellm.

---

## Path to enterprise-grade — next 5 milestones

1. **Upgrade skew on `/ready`** — `schema_ok` when a local store lags the
   binary (row 125). No downgrade command until a fleet asks.
2. **Client recipes that match the protocol** — OpenCode print-only
   (row 122); Gemini CLI must not aim `GOOGLE_GEMINI_BASE_URL` at daari
   (row 123). Cursor-agent CLI stays on watch.
3. **Operator-facing probe contract** — one page for `/ready` statuses
   (row 124).
4. **Admin-plane depth** — end-user inventory, guardrail profiles, web-ui
   pagination, report bounds, multi_agent pricing (rows 62–67) as the
   `agent:working` sessions land.
5. **Trace-native packaging** — Responses background webhooks, Prometheus
   exemplars, `gen_ai.agent.*` spans (watch rows → file as sessions open).

Compliance non-goals (SCIM, WIF depth, A2A, SOC 2 program, Realtime/WS,
FIPS builds, HIPAA BAA) stay deferred until buyer demand.

---

## Changelog

- **2026-10-17 (client recipes + upgrade skew)** — Marked rows 117–121 and
  the same-day follow-through Shipped (fast mode, `:cloud` metering, scoped
  reads, unlock, Helm `--consistent`, doctor `--strict`, Codex, gzip, events
  audit, LiteLLM 1.105.0 GA compare). Filed OpenCode print-only configure,
  Gemini CLI native-API honesty, a `/ready` status page, and `schema_ok`.
  Outward: OpenCode v2 `providers.*.settings.baseURL`; Gemini CLI remains
  native-API-only; LiteLLM stable line still 1.105.x.

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
