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

## Where daari stands (verified in-tree, 2026-10-26 pm)

**Loop velocity.** Morning's fill (rows 217–221: background-job lease, at-rest
encryption, Helm webhook secrets, wave integration fence, Phonon coercion
honesty) is still open alongside the three P3s (voices console, skills CLI,
TTS Prom counters). No feature merge since the morning PRD squash.

**Outward.** OpenAI shipped **GPT-6.1 Terra** today (`gpt-6.1-terra`): $1/$5
Standard, $0.05 cached, 30m/12h cache writes $1.25/$2.50, >272K at 2×/1.5×,
`reasoning.effort` includes `none`, tools require Responses — daari still only
catalogs `gpt-5.6-terra`. LiteLLM floor remains **1.106.4** (1.107.0
do-not-install); Ollama **0.40.11**; Kong AI Gateway **2.2.0**; vLLM **0.32.0**.
SEP-2640 **Skills over MCP** is an official MCP extension; our `/mcp` surface
loads AAIF packages into the prompt but does not speak `skills/*` or
`skill://`. Anthropic Skills API remains GA (watch for `/v1/skills` proxy
demand).

**Inward theme: price the new model, finish FinOps UX, speak Skills over MCP,
honest scrape text.** Grouped spend reports exist on CLI + HTTP but the web-ui
has zero `group_by`/`bucket` controls. `daari_schema_ok` already covers
Postgres skew while HELP/Grafana still say "SQLite only". Phonon coercion
needs a scrapeable counter next to any client warning.

---

## Scored gap table

| # | Gap | Impact | Effort | Who does it best today | Why daari wins local-first | Action |
|---|-----|:--:|:--:|------------------------|----------------------------|--------|
| 222 | Day-one `gpt-6.1-terra` prices, >272K threshold, capabilities, param_compat | 4 | 2 | OpenAI model cards / LiteLLM day-one | Invoice-true on-box ledger | Filed [#1963](https://github.com/naveenreddyalka/daari/issues/1963) |
| 223 | Web-ui grouped spend report controls (`group_by` / `bucket`) | 3 | 2 | LiteLLM admin UI | Same-box console over existing report API | Filed [#1964](https://github.com/naveenreddyalka/daari/issues/1964) |
| 224 | Skills over MCP (SEP-2640): `skills/list` + `skill://` resources | 4 | 3 | Bloomberg / Anthropic MCP extension | On-disk skills via local `/mcp` grants | Filed [#1965](https://github.com/naveenreddyalka/daari/issues/1965) |
| 225 | `daari_schema_ok` HELP + Grafana copy cover Postgres skew | 2 | 1 | — (ops honesty) | Gauge already right; text lagged | Filed [#1966](https://github.com/naveenreddyalka/daari/issues/1966) |
| 226 | Prometheus counter when Phonon coerces `response_format` | 2 | 1 | OpenRouter transform metrics | Local scrape next to TTS path | Filed [#1967](https://github.com/naveenreddyalka/daari/issues/1967) |
| 217 | Responses background jobs: `in_progress` + lease/heartbeat + orphan reclaim | 4 | 2 | OpenAI background mode | Fleet-true jobs on stores we run | Filed (morning) |
| 218 | At-rest encryption of payload stores with customer-held key | 4 | 3 | OpenAI EKM | Key never leaves the box via `secret://` | Filed (morning) |
| 219 | Helm `webhooks.*` URL + signing-secret knobs (five families) | 3 | 1 | LiteLLM raw env config | Finish `secretKeyRef` push story | Filed (morning) |
| 220 | Gateway-flow coverage for the 10-25/26 wave | 3 | 2 | — (regression fence) | Mockable in-process daily fence | Filed (morning) |
| 221 | Client-visible warning when Phonon coerces `response_format` | 2 | 1 | OpenRouter transform warnings | Honesty-by-header | Filed (morning) |
| 206–216 | 10-24/25 wave (trust scrub, grouped reports, breakers, user_id, webhooks, Phonon, Skills, TTS bench) | 2–4 | 1–2 | LiteLLM / Anthropic / OpenAI / Kong | Trust floor, FinOps, push, voice | Shipped |
| 198–205 | eMudhra distrust; fleet breakers; Phonon voices; compare 1.106.3; user RPD; webhook harden; TTS bounds | 3–4 | 1–3 | LiteLLM / Anthropic / OpenAI / Svix | Trust floor, HA, voice, push | Shipped |
| 62 | End-user inventory + per-user block/cap overrides | 5 | 3 | OpenRouter / LiteLLM | Ledger already knows every user | Open |
| 63 | Named guardrail profiles bindable per key/team | 5 | 3 | OpenRouter / Portkey | Per-tenant policy, zero hops | Open |
| 65 | Web-ui: honor keys/teams `has_more` + render `report.users` | 4 | 2 | LiteLLM admin UI | Same-box console finishes the job | Open |
| 66 | Bound/paginate report `clients`/`users` rollups | 4 | 2 | LiteLLM paged usage | Fleet-safe JSON on-box | Open |
| 67 | multi_agent nested usage: per-subagent `model` | 4 | 2 | OpenAI / LiteLLM FinOps | Ledger already meters nested tokens | Open |
| 6 | Hot-reload `config.yaml` | 3 | 2 | LiteLLM config ownership | Open — needs long session | Open |
| 7 | Per-key tool-name allowlist for Messages `mcp_servers` | 4 | 3 | LiteLLM `mcp_tool_permissions` | Parked (≥60m session) | Parked |
| 8 | Full DCR; A2A; Realtime/WS; stdio MCP; M365; FIPS; HIPAA BAA | 2–4 | 3–5 | Portkey / Kong / LiteLLM | Demand-triggered | Watch |
| 136–197 | 10-18 → 10-24 protocol/FinOps/HA/voice waves | 2–5 | 1–3 | LiteLLM / Portkey / Kong / vLLM / OpenAI | Shipped | Shipped |

Watch rows (do not file yet): OpenAI `/agents/automations` passthrough
(demand-triggered); Prisma AIRS Agent Identity Security; **Claude Models on
Google Cloud (Anthropic managed)** as a frontier flavor (IAM-auth egress —
likely needs a Google auth dependency, human sign-off); Anthropic hosted
`/v1/skills` proxy (we filed local SEP-2640 first); Open Responses WebSocket;
Anthropic OTel export beta parity; Prometheus exemplars + `gen_ai.agent.*`;
LiteLLM 1.107-rebuild watchables (ID-JAG / OAuth-delegate /
`agent_access_default_deny`); Portkey WIF upstream creds; SCIM + multi-issuer
SSO; Kong Skills/A2A passthrough demand; OpenRouter Private Endpoints as an L6
slot recipe; certifi upstream drop of emSign roots; llama.cpp `mtmd`
capability helpers (wait for Ollama surface).

Verified fine this run — don't re-audit: LiteLLM compare floor **1.106.4**;
Ollama 0.40.11 Responses reasoning-effort fallback is upstream-only (our
param_compat table is the right place for Terra); grouped-report HTTP route
and CLI flags; `user_rpd` admin + web-ui; console breaker inventory/reset;
nine-client `daari configure`; skills loader flat + AAIF packages; cross-pod
Responses *polling* (lifecycle/lease still row 217); 12-hour caching billed;
`schema_ok` semantics complete (copy only, row 225).

---

## Path to enterprise-grade — next 5 milestones

1. **Price what OpenAI shipped today** — day-one `gpt-6.1-terra` catalog so
   FinOps and param_compat match the model card (row 222).
2. **Jobs that survive pods** — `in_progress` + lease/heartbeat + orphan
   reclaim for background Responses jobs (row 217).
3. **Encrypt what we keep** — opt-in at-rest encryption with a customer-held
   `secret://` key (row 218).
4. **Finish FinOps UX + Skills discovery** — web-ui grouped reports (row 223)
   and Skills over MCP (row 224); Helm webhook secrets (row 219).
5. **Fence + honesty** — wave integration coverage (row 220), Phonon coercion
   warning + Prom counter (rows 221, 226), schema_ok copy (row 225), then
   tenancy set (rows 62–67) and hot-reload (row 6).

Compliance non-goals (SCIM, WIF depth, A2A, SOC 2 program, Realtime/WS,
FIPS builds, HIPAA BAA, Open Responses WS, Claude-on-GCP without human
dep sign-off) stay deferred until buyer demand.

---

## Changelog

- **2026-10-26 pm (price Terra, finish FinOps UX, speak Skills over MCP)** —
  Outward delta: OpenAI GPT-6.1 Terra GA ($1/$5, >272K surcharge, Responses
  tools). LiteLLM/Ollama/Kong/vLLM unchanged. Promoted SEP-2640 Skills over
  MCP from watch. Filed rows 222–226 (Terra catalog, web-ui grouped spend,
  Skills over MCP, schema_ok HELP/Grafana copy, Phonon coercion Prom
  counter). Morning rows 217–221 remain open; no feature merges since the
  morning squash.

- **2026-10-26 (keep jobs alive, encrypt what we keep, mount the secrets)** —
  Marked rows 206–216 Shipped. Outward flat at morning scan. Filed rows
  217–221 (lease/orphan reclaim, EKM-analog encryption, Helm webhook knobs,
  wave coverage, Phonon coercion honesty).

- **2026-10-25 (prove the wave, report on it, ship a clean image)** — Marked
  rows 198–205 and the console/PG pair Shipped. Outward: LiteLLM 1.106.4
  image hygiene; Ollama 0.40.11; OpenAI EKM + UK residency; Prisma AIRS.
  Filed rows 207–211; adopted pm sibling rows 212–216.

- **2026-10-24 + pm → 08-28** — Condensed: trust floors, HA share, local
  voice, push channels; bill-what-was-served; LiteLLM compromise; Apache 2.0;
  this PRD's creation.
