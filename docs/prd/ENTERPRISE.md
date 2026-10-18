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

## Where daari stands (verified in-tree, 2026-10-18 evening)

**Loop velocity.** Morning board is on main: `tools/call` `resultType`
(row 136) and compare-litellm 1.106.0 GA floor (row 139). Still open from
the morning filing: fast-mode rate-limit header copy, adaptive thinking
key strip, chat-completions header copy, header docs, and `tasks/get`
`resultType`. `agent:working` rows 6/62–63/65–67 unchanged.

**Outward.** LiteLLM stable stays **1.106.0 GA**. **1.107.0-rc.1 (10-18)**
is still prerelease: empty trailing user content, count-token honesty,
web-search tool cost, and provider request ids on stream failures are the
slices worth taking now. `agent_access_default_deny` stays on watch until
1.107 is GA. **Ollama 0.40.7-rc0** unchanged (do not file). Portkey v2.20.0
enterprise notes, Kong 2.2.0, vLLM 0.31.0, and OpenRouter unchanged since
the morning scan. Anthropic platform notes still stop at 10-15.

**Inward theme: replay and ledger honesty.** Trailing empty user turns are
dropped before Anthropic egress. `count_tokens` ignores image and document
blocks. Web-search calls are absent from frontier cost. Frontier HTTP
failures omit the provider request id. `speed` on a non-Anthropic L6 slot
is silent.

---

## Scored gap table

| # | Gap | Impact | Effort | Who does it best today | Why daari wins local-first | Action |
|---|-----|:--:|:--:|------------------------|----------------------------|--------|
| 140 | Keep trailing user turns whose content is null, `""`, or `[]` | 4 | 1 | LiteLLM 1.107-rc.1 empty content | Agent loops replay without a 400 | Filed [#1768](https://github.com/naveenreddyalka/daari/issues/1768) |
| 141 | `count_tokens` includes image and document blocks | 3 | 2 | LiteLLM 1.107-rc.1 count honesty | Vision budget is known before any hop | Filed [#1769](https://github.com/naveenreddyalka/daari/issues/1769) |
| 142 | Bill frontier web-search calls at $0.01 on the local ledger | 4 | 2 | LiteLLM 1.107-rc.1 tool cost | Spend matches the invoice on-box | Filed [#1770](https://github.com/naveenreddyalka/daari/issues/1770) |
| 143 | Record upstream request ids on frontier HTTP failures | 3 | 1 | LiteLLM 1.107-rc.1 failure logs | Provider tickets cite the id the box already saw | Filed [#1771](https://github.com/naveenreddyalka/daari/issues/1771) |
| 144 | Warn when `speed` is set and L6 is not Anthropic | 3 | 1 | Anthropic fast mode | Clients learn the fast bucket was not used | Filed [#1772](https://github.com/naveenreddyalka/daari/issues/1772) |
| 136 | MCP `2026-07-28` `tools/call` results include `resultType` | 4 | 2 | Claude Code 2.1.302 | On-box tool loop matches the call-result contract | Shipped |
| 137 | Copy Anthropic fast-mode rate-limit headers onto the client response | 3 | 2 | Anthropic fast-mode headers | Client backs off from the box that already made the hop | Open |
| 138 | Drop unknown keys when outbound `thinking.type` is `adaptive` | 3 | 1 | LiteLLM 1.107-rc.1 drop_params | Mixed thinking objects succeed without a 400 | Open |
| 139 | compare-litellm: 1.106.0 GA floor; 1.107 stays RC | 2 | 1 | LiteLLM 1.106.0 release | Honest local-first comparison | Shipped |
| 131 | Ollama `:cloud` counts as remote egress for `no_frontier` / PII scrub / region fences | 5 | 2 | Portkey egress fences | "Local-only means local-only" is the core promise | Shipped |
| 132–135 | Streamed fast billing; events/lockouts UI; 529 degrade; fast-mode catalog | 3–4 | 1–2 | Anthropic / LiteLLM | Billing and ops on-box | Shipped |
| 126–130 | List `resultType`; doctor `:cloud`/`q2_0`; spend `reset_at`; `:floor`/`:nitro` cards | 2–4 | 1–2 | Claude Code / Ollama / LiteLLM | Protocol and catalog truth on-box | Shipped |
| 122–125 | OpenCode print-only; Gemini honesty; `/ready` page; `schema_ok` | 2–4 | 1–3 | — | Client recipes and upgrade skew | Shipped |
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

Watch rows (do not file yet): gzip compression Prom metrics (ratio/CPU —
operator ask); warn when `speed` is requested but the active L6 provider is
not Anthropic (fold into the next param-compat slice); `CONFIGURE_CLIENTS`
first-wave tuple lags the registry (trivial, fold into the next recipe);
cursor-agent CLI configure (distinct from
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
cleartext; gzip JSON over 16 KiB; Codex and OpenCode print-only configure;
events list audit row and team filters on keys/teams/audit; LiteLLM 1.105.0
marked GA in compare-litellm; `/v1/systemone` question maps already accept
identifier keys; signed empty thinking blocks with a signature are kept.
Evening pass verified fine: gzip exempts SSE/pre-encoded bodies, sets
`Vary`, passes through multi-chunk streams (incl. deferred-header streams);
lockout already pages via a signed webhook; budget rollups and cost headers
include `:cloud` spend; non-stream fast-mode billing is cost-true; pricing
falls back to standard when `usage.speed` is absent.

---

## Path to enterprise-grade — next 5 milestones

1. **Replay honesty** — keep a trailing user turn when content is null,
   `""`, or `[]` (row 140) so Anthropic and local tiers see the same last
   role the agent sent.
2. **Fast-mode client backoff** — copy the six `anthropic-fast-*-tokens-*`
   headers onto Messages responses (row 137) and warn when `speed` is set
   on a non-Anthropic L6 slot (row 144).
3. **Adaptive thinking payload hygiene** — drop non-`type` keys when
   outbound `thinking.type` is `adaptive` (row 138). Leave `type: enabled`
   budgets and assistant thinking blocks alone.
4. **Ledger honesty** — add $0.01 per frontier web-search call (row 142)
   and include image and document blocks in local `count_tokens` (row 141).
5. **Failure correlation** — put the upstream request id on frontier HTTP
   failures (row 143). Admin-plane rows 62–67 stay with their
   `agent:working` sessions. Trace-native packaging stays on watch.

Compliance non-goals (SCIM, WIF depth, A2A, SOC 2 program, Realtime/WS,
FIPS builds, HIPAA BAA) stay deferred until buyer demand.

---

## Changelog

- **2026-10-18 evening (replay, count, and ledger honesty)** — Marked
  rows 136 and 139 Shipped (`tools/call` `resultType`, compare-litellm
  1.106.0 GA floor). Filed rows 140–144: trailing empty user turns,
  image/document `count_tokens`, web-search call fees, upstream request
  ids on frontier HTTP failures, and a `speed` warning when L6 is not
  Anthropic. Outward: LiteLLM 1.107.0-rc.1 still prerelease; Ollama
  0.40.7-rc0, Portkey, Kong 2.2.0, vLLM 0.31.0, and OpenRouter unchanged.

- **2026-10-18 (1.106 GA, call-result resultType, fast-mode headers)** —
  Marked rows 123–135 Shipped (egress fences, stream billing, 529 degrade,
  events/lockout surfaces, catalog/doctor/ready honesty). Filed rows
  136–139: `tools/call` `resultType`, Anthropic fast-mode rate-limit header
  copy, adaptive thinking key strip, compare-litellm 1.106.0 GA.
  Outward: LiteLLM 1.106.0 GA and 1.107.0-rc.1; Ollama 0.40.7-rc0 left on
  watch. Anthropic, Portkey, Kong, vLLM, and OpenRouter unchanged.

- **2026-10-17 evening (depth behind the 24h wave: egress truth, stream
  billing, ops surfaces)** — Third scan today; outward flat since the
  afternoon run (LiteLLM v1.103.5 is a Responses backport patch, stable
  stays 1.105.1; Portkey v2.29.0, Kong 2.2.0, vLLM 0.31.0 unchanged).
  Drained the dead 10-16 eve sibling PRD PR to main. Filed rows 131–135:
  `:cloud` remote-egress fences, streamed fast-mode `usage.speed` billing,
  events/lockout operator surfaces, 529 retry + fast→standard degrade,
  fast-mode catalog capability. Verified fine: gzip edges, lockout webhook
  paging, `:cloud` spend rollups, non-stream fast billing.

- **2026-10-17 (protocol cache hints + Ollama cloud/quant honesty)** —
  Marked OpenCode print-only (row 122) Shipped. Filed MCP `2026-07-28`
  list `resultType`, doctor `:cloud` pull honesty, `team_model_spend`
  `reset_at`, `:floor`/`:nitro` catalog metadata, and an optional doctor
  warning below Ollama 0.40.6 for `q2_0` GGUF. Outward: Claude Code
  2.1.302, Ollama 0.40.6, LiteLLM 1.107.0-dev.3 budget-reset reporting.
  Anthropic, Portkey, Kong, vLLM, and OpenRouter unchanged since the
  morning scan.

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
