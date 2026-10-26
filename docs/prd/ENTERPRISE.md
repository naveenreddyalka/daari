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

## Where daari stands (verified in-tree, 2026-10-26)

**Loop velocity.** The whole 10-25 wave (rows 206–216) merged within a day:
image trust-store scrub + compare floor 1.106.4, gateway-flow coverage for the
10-24/25 wave (`test_wave_gateway_coverage.py`), dimension-grouped spend
reports with `service_tier` persisted (CLI `--group-by/--bucket` **and**
`GET /v1/daari/spend/report`), per-family breaker state/alerts/reset (fleet
inventory + reset in the console), Anthropic `metadata.user_id` fences with
`user_rpd` in admin reads and the web-ui, completion-webhook doctor parity,
webhook Grafana/alerts, Phonon language tags + CC BY-NC tip, AAIF Agent
Skills packages, the hermetic TTS benchmark, and Phonon `response_format`
coercion. The loop refilled three P3s this morning (voices console, skills
CLI list, TTS Prom counters).

**Outward.** Flat since yesterday's scan. LiteLLM floor stays **1.106.4**
(1.107.0 do-not-install); OpenAI changelog shows nothing after the 10-22
Decisions GA; Anthropic flat since the 10-22 **Claude Models on Google Cloud
(Anthropic managed)** GA — full platform via Google Cloud IAM/Marketplace
billing, Opus 5.5 fast mode at $8/$40; Ollama holds at **0.40.11**; Kong at
2.2.0 (passthrough mode); vLLM at 0.32.0; llama.cpp b11899 adds multimodal
capability helpers (no router impact).

**Inward theme: keep jobs alive, keep secrets mounted, encrypt what we keep.**
Background Responses jobs persist `queued` → terminal only — no
`in_progress`, no lease, so a dead owning pod leaves the job queued
fleet-wide forever. Every persisted payload store (response store, request
log, L1 disk cache) is plaintext on disk the day after OpenAI shipped
Enterprise Key Management. The Helm chart mounts API keys via `secretKeyRef`
but has zero plumbing for the five webhook signing-secret families. The
newest wave (grouped reports route, breaker reset, skills packages, Phonon
tags/coercion) has no integration fence yet, and the format coercion is
silent to the caller.

---

## Scored gap table

| # | Gap | Impact | Effort | Who does it best today | Why daari wins local-first | Action |
|---|-----|:--:|:--:|------------------------|----------------------------|--------|
| 217 | Responses background jobs: `in_progress` + lease/heartbeat + orphan reclaim on poll | 4 | 2 | OpenAI background mode | Fleet-true jobs on the stores we already run; no external queue | Filed [#1957](https://github.com/naveenreddyalka/daari/issues/1957) |
| 218 | At-rest encryption of payload stores (response store, request log, disk cache) with a customer-held key | 4 | 3 | OpenAI EKM (10-24) | Key never leaves the box via `secret://`; no vendor sees plaintext | Filed [#1958](https://github.com/naveenreddyalka/daari/issues/1958) |
| 219 | Helm `webhooks.*` URL + signing-secret knobs for all five webhook families | 3 | 1 | LiteLLM raw env config | `secretKeyRef` pattern exists (frontier/systemone); finish the push story | Filed [#1959](https://github.com/naveenreddyalka/daari/issues/1959) |
| 220 | Gateway-flow coverage for the 10-25/26 wave (grouped report route, breaker reset, user_id fences, skills, Phonon tags/coercion) | 3 | 2 | — (regression fence) | All mockable in-process; the fence that lets the loop merge daily | Filed [#1960](https://github.com/naveenreddyalka/daari/issues/1960) |
| 221 | Client-visible warning + counter when Phonon coerces `response_format` | 2 | 1 | OpenRouter transform warnings | Honesty-by-header beats silent substitution | Filed [#1961](https://github.com/naveenreddyalka/daari/issues/1961) |
| 206–216 | 10-24/25 wave: strip visibility, image trust-store scrub, wave coverage, grouped reports, breaker observability, user_id fences, webhook doctor + panels, Phonon tags, AAIF Skills, TTS benchmark | 2–4 | 1–2 | LiteLLM / Anthropic / OpenAI / Kong | Trust floor, FinOps truth, push channels, local voice | Shipped |
| 198–205 | eMudhra egress distrust; fleet breakers; Phonon voices; compare 1.106.3; user RPD; webhook delivery + ingest hardening; TTS bounds | 3–4 | 1–3 | LiteLLM / Anthropic / OpenAI / Svix | Trust floor, HA share, local voice, push channels | Shipped |
| 62 | End-user inventory + per-user block/cap overrides | 5 | 3 | OpenRouter / LiteLLM | Ledger already knows every user | Open |
| 63 | Named guardrail profiles bindable per key/team | 5 | 3 | OpenRouter / Portkey | Per-tenant policy, zero hops | Open |
| 65 | Web-ui: honor keys/teams `has_more` + render `report.users` | 4 | 2 | LiteLLM admin UI | Same-box console finishes the job | Open |
| 66 | Bound/paginate report `clients`/`users` rollups | 4 | 2 | LiteLLM paged usage | Fleet-safe JSON on-box | Open |
| 67 | multi_agent nested usage: per-subagent `model` | 4 | 2 | OpenAI / LiteLLM FinOps | Ledger already meters nested tokens | Open |
| 6 | Hot-reload `config.yaml` | 3 | 2 | LiteLLM config ownership | Open — needs long session | Open |
| 7 | Per-key tool-name allowlist for Messages `mcp_servers` | 4 | 3 | LiteLLM `mcp_tool_permissions` | Parked (≥60m session) | Parked |
| 8 | Full DCR; A2A; Realtime/WS; stdio MCP; M365; FIPS; HIPAA BAA | 2–4 | 3–5 | Portkey / Kong / LiteLLM | Demand-triggered | Watch |
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
| 136–197 | 10-18 → 10-24 protocol/FinOps/HA/voice waves | 2–5 | 1–3 | LiteLLM / Portkey / Kong / vLLM / OpenAI | Shipped | Shipped |

Watch rows (do not file yet): OpenAI `/agents/automations` passthrough (spec
10-23; demand-triggered); Prisma AIRS **Agent Identity Security** (per-agent
OAuth 2.1 identity + dual-attribution audit; adjacent to the parked per-key
tool allowlist row); `daari_schema_ok` gauge HELP text still says "SQLite"
though it covers PG skew (fold into the next observability slice); **Claude
Models on Google Cloud (Anthropic managed)** as a frontier flavor (GA 10-22,
IAM-auth egress + Marketplace billing, Opus 5.5 fast $8/$40 — buyer ask;
likely needs a Google auth dependency, so human sign-off); Anthropic threads
are **Managed Agents session threads + SSE**, not Messages API threads; Open
Responses WebSocket; Anthropic OTel export beta parity; Prometheus exemplars
+ `gen_ai.agent.*`; LiteLLM 1.107-rebuild watchables (ID-JAG / OAuth-delegate
/ `agent_access_default_deny`); Portkey WIF upstream creds; SCIM +
multi-issuer SSO; Kong Skills/A2A passthrough demand; OpenRouter Private
Endpoints as an L6 slot recipe; certifi upstream drop of emSign roots (our
image scrub shipped — watch for the certifi release to drop the Dockerfile
workaround); llama.cpp `mtmd` capability helpers (watch for an Ollama-side
surface before acting).

Verified fine this run — don't re-audit: day-2 of the 10-25 wave is already
in: `GET /v1/daari/spend/report` takes `group_by`/`bucket` with 400 guards;
`user_rpd` renders in `admin_read` keys rows and the web-ui; the console has
the fleet-breakers inventory + reset with 403 handling; `daari configure`
covers all nine registry clients (cursor/claude-code/vscode/claude-desktop/
chatgpt-desktop/codex/gemini-cli/intellij/opencode); Phonon coercion serves
the **correct** Content-Type (upstream header wins; gap is the missing
warning only, row 221); skills loader takes flat `*.md` + package
`SKILL.md` dirs, immediate children only. Cross-pod Responses *polling*
works via the persisted store (gap is lifecycle/lease only, row 217).
OpenAI 12-hour caching billed; incremental streaming guardrails; `gb`
residency via free-form labels; d3 GA sizes in `BUILTIN_LOCAL_MODELS`;
`schema_ok` observability complete.

---

## Path to enterprise-grade — next 5 milestones

1. **Jobs that survive pods** — `in_progress` + lease/heartbeat + orphan
   reclaim for background Responses jobs; HA truth for the one async
   surface that still assumes a single long-lived process (row 217).
2. **Encrypt what we keep** — opt-in at-rest encryption of the payload
   stores with a customer-held `secret://` key; the local-first answer to
   OpenAI EKM for regulated buyers (row 218).
3. **Mount the push channel** — Helm knobs for every webhook URL and
   signing secret so fleets stop inlining secrets in `extraEnv` (row 219).
4. **Fence the new wave** — integration coverage for grouped reports,
   breaker reset, dual-door user fences, skills, and Phonon paths
   (row 220), plus coercion honesty (row 221).
5. **Finish the tenancy set** — end-user inventory/overrides, guardrail
   profiles, paged rollups and console rendering (rows 62–67), then
   hot-reload (row 6).

Compliance non-goals (SCIM, WIF depth, A2A, SOC 2 program, Realtime/WS,
FIPS builds, HIPAA BAA, Open Responses WS) stay deferred until buyer demand.

---

## Changelog

- **2026-10-26 (keep jobs alive, encrypt what we keep, mount the secrets)** —
  Marked rows 206–216 Shipped (whole 10-25 wave merged within a day,
  including the pm sibling's five rows). Outward flat: LiteLLM 1.106.4
  floor holds, OpenAI/Anthropic/Ollama/Kong/vLLM unchanged since
  yesterday's scan; noted Claude-on-Google-Cloud GA details and llama.cpp
  mtmd helpers as watch. Promoted two watch rows to filings now that the
  backlog drained: background-job lease/orphan reclaim (row 217) and
  EKM-analog at-rest encryption (row 218). Also filed Helm webhook-secret
  knobs (row 219), wave integration coverage (row 220), and Phonon
  coercion honesty (row 221). Verified shipped day-2: grouped-report HTTP
  route, user_rpd admin visibility, console breaker inventory/reset,
  complete configure recipes.

- **2026-10-25 (prove the wave, report on it, ship a clean image)** — Marked
  rows 198–205 and the console/PG pair Shipped. Outward: LiteLLM 1.106.4
  image hygiene; Ollama 0.40.11 GA (parity held); OpenAI EKM + UK residency
  + `/agents/automations`; Prisma AIRS Agent Identity Security. Filed rows
  207–211; adopted the pm sibling's rows 212–216 after its PRD branch
  pruned the pinned rows and failed the pin test.

- **2026-10-24 + pm (trust floors, HA share, local voice; push channels)** —
  Marked rows 191–197 Shipped. Outward: LiteLLM 1.106.3 GA floor, Ollama
  0.40.10/0.40.11-rc0, AAIF Skills + Open Responses WS, Anthropic SDK
  2.2.0/2.3.0, Claude on Google Cloud. Filed rows 198–206; the pm breaker
  filing duplicated row 199 and needs a human close.

- **2026-10-23 → 08-28** — Condensed: bill-what-was-served + GA parity;
  finish-the-truths, console and day-2 packaging; breaker truth,
  invoice-true cache billing, user profiles; LiteLLM compromise + Anthropic
  API-version footgun; finish-the-knobs; decisions depth;
  `resultType`/egress waves; Apache 2.0; this PRD's creation.
