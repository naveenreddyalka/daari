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

## Where daari stands (verified in-tree, 2026-10-24)

**Loop velocity.** Yesterday's "bill what was served / speak what went GA"
set plus the watch drain all landed on main today: served-tier billing,
Decisions GA parity, d3+Flint, streamed Phonon TTS, wave Grafana alerts,
fleet Responses cancel, enforcement webhook ingest, signed Responses
completion webhooks, Anthropic 2026-10-21 document/citation strips, and the
Nemotron 3.5 Bolt E4B VLM recipe. Eligible open backlog is thin (console
enforcement panel, Postgres `schema_ok`/`migrate --downgrade`, plus the
long-running 10-10 tenancy set still `agent:working`).

**Outward.** LiteLLM **1.106.3** (2026-10-24) is the new GA floor: cosign
signing key rotated to commit `e82a3c6`, and the **eMudhra root CA is
removed** from every LiteLLM trust bundle (also backported to 1.103.8 /
1.104.6 / 1.105.4). Treat **1.107.0** as still compromised / do-not-install.
Ollama **0.40.10** GA shipped Nemotron Bolt E4B; **0.40.11-rc0** adds a
Phonon voice catalog + mlxrunner spelling for symbols/numbers/links.
AAIF (10-22) took Agent Skills, Open Responses, OpenEnv, OpenSandbox —
Open Responses adds WebSocket transport + compaction under neutral
governance. Anthropic OTel export for Messages/Managed Agents is in beta.
vLLM 0.32.0, Kong 3.16.0.1 (A2A v1.0), semantic-router 1.0/1.1, OpenRouter
Private Endpoints — flat vs daari's local-first wedge. certifi 2026.10.23
still ships eMudhra roots; LiteLLM already acted.

**Inward theme: match the trust floors, finish HA share, speak local voice.**
Default httpx/certifi egress still trusts a CA LiteLLM just dropped. Frontier /
local-pool / MCP breakers remain process-local after systemone proved the
Redis pattern. Speech has no voice list/map for Phonon's new catalog.
Compare docs still pin 1.106.2. End-users have USD day caps but no request
day caps.

---

## Scored gap table

| # | Gap | Impact | Effort | Who does it best today | Why daari wins local-first | Action |
|---|-----|:--:|:--:|------------------------|----------------------------|--------|
| 198 | Distrust eMudhra/emSign on egress TLS + doctor tip | 4 | 1 | LiteLLM 1.106.3 / Kong / Portkey | One-process TLS policy; no cloud image wait | Filed [#1907](https://github.com/naveenreddyalka/daari/issues/1907) |
| 199 | Fleet-share frontier / local-pool / MCP egress breakers via Redis | 4 | 3 | Kong / cloud gateways | Same Redis as cache; blast-radius on-box | Filed [#1908](https://github.com/naveenreddyalka/daari/issues/1908) |
| 200 | Phonon voice catalog list + OpenAI voice-name map | 3 | 2 | OpenAI TTS / Ollama 0.40.11-rc0 | Local voices behind daari auth/budgets | Filed [#1909](https://github.com/naveenreddyalka/daari/issues/1909) |
| 201 | compare-litellm: pin GA floor at 1.106.3 (cosign + eMudhra) | 3 | 1 | LiteLLM release notes | Honest GTM without a LiteLLM runtime dep | Filed [#1910](https://github.com/naveenreddyalka/daari/issues/1910) |
| 202 | Per-end-user RPD alongside `user_daily_usd_cap` | 4 | 2 | LiteLLM / OpenRouter | Ledger already attributes `user` | Filed [#1911](https://github.com/naveenreddyalka/daari/issues/1911) |
| 193–197 | Served-tier spend; Decisions GA; d3+Flint; streamed TTS; wave panels/alerts | 3–4 | 1–2 | OpenAI / Ollama / Grafana | Invoice, GA shape, $0 judge, local voice, day-2 | Shipped |
| 191–192 | Fleet Responses cancel; Anthropic enforcement webhook ingest | 4 | 3 | OpenAI / Anthropic Admin | Redis cancel; push→tenant map | Shipped |
| 188–190 | Console export/reset; Grafana gzip+TTL; vLLM 0.32.0 floor doc | 3 | 1–2 | LiteLLM UI / Grafana / vLLM | Day-2 packaging | Shipped |
| — | Web-ui enforcement inventory + cache-invalidate form | 3 | 2 | LiteLLM admin UI | Same-box console | Open (filed prior run) |
| — | Postgres `schema_ok` skew gate + `migrate --downgrade` | 3 | 2 | LiteLLM migrate story | Ready truth for PG fleets | Open (filed prior run) |
| 62 | End-user inventory + per-user block/cap overrides | 5 | 3 | OpenRouter / LiteLLM | Ledger already knows every user | Open |
| 63 | Named guardrail profiles bindable per key/team | 5 | 3 | OpenRouter / Portkey | Per-tenant policy, zero hops | Open |
| 65 | Web-ui: honor keys/teams `has_more` + render `report.users` | 4 | 2 | LiteLLM admin UI | Same-box console finishes the job | Open |
| 66 | Bound/paginate report `clients`/`users` rollups | 4 | 2 | LiteLLM paged usage | Fleet-safe JSON on-box | Open |
| 67 | multi_agent nested usage: per-subagent `model` | 4 | 2 | OpenAI / LiteLLM FinOps | Ledger already meters nested tokens | Open |
| 6 | Hot-reload `config.yaml` | 3 | 2 | LiteLLM config ownership | Open — needs long session | Open |
| 7 | Per-key tool-name allowlist for Messages `mcp_servers` | 4 | 3 | LiteLLM `mcp_tool_permissions` | Parked (≥60m session) | Parked |
| 8 | Full DCR; A2A; Realtime/WS; stdio MCP; M365; Skills; FIPS; HIPAA BAA | 2–4 | 3–5 | Portkey / Kong / LiteLLM | Demand-triggered | Watch |
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
| 136–182 | 10-18 → 10-21 protocol/FinOps/HA waves | 2–5 | 1–3 | LiteLLM / Portkey / Kong / vLLM | Shipped | Shipped |

Watch rows (do not file yet): AAIF **Agent Skills** package loader beyond flat
`~/.daari/skills/*.md` prefix (donate-standard SKILL.md + scripts — demand
after Skills show up in buyer IDEs); Open Responses **WebSocket** transport
(AAIF/OpenAI; keep HTTP Responses first); Anthropic **OTel export** beta
parity for Messages spans; Prometheus **exemplars** + `gen_ai.agent.*`
depth; Nemotron **DFlash** speculative-decoding tip once 0.40.10 recipes
settle; LiteLLM clean **post-compromise 1.107 rebuild** watchables
(ID-JAG / OAuth-delegate / `agent_access_default_deny`) — stay on 1.106.3
until a verified rebuild; Portkey WIF upstream creds (buyer ask); SCIM +
multi-issuer SSO; Kong Skills/A2A passthrough demand; OpenRouter Private
Endpoints as an L6 slot recipe.

Verified fine this run — don't re-audit: served-tier spend + stream cost
headers after degrade; Decisions GA (`input_json`, images, 400 ceiling,
cached-input billing); d3 family + Flint Linux/Windows; streamed
`/v1/audio/speech` + Phonon tip; Grafana panels/alerts for degrade /
sampling-strip / enforced-profiles; fleet Responses cancel; enforcement
webhook ingest; signed Responses completion webhooks; Anthropic
document/citation strips under `2026-10-21`; Nemotron Bolt E4B recipe;
systemone Redis breaker; cache-write TTL billing on stream shapes.

---

## Path to enterprise-grade — next 5 milestones

1. **Match the trust floors** — eMudhra distrust on egress + doctor tip
   (row 198) and refresh compare-litellm to 1.106.3 (row 201).
2. **Finish HA share** — fleet-share the remaining process-local breakers
   (row 199) using the proven systemone Redis pattern.
3. **Local voice discoverability** — Phonon voice catalog + OpenAI name map
   (row 200) on top of streamed TTS.
4. **Tighten end-user fences** — per-user RPD (row 202) beside USD day caps;
   keep draining the 10-10 tenancy/console set (62–67).
5. **Day-2 console + PG ready truth** — enforcement inventory panel and
   Postgres schema_ok / migrate downgrade (prior-run filings).

Compliance non-goals (SCIM, WIF depth, A2A, SOC 2 program, Realtime/WS,
FIPS builds, HIPAA BAA, full AAIF Skills/Open Responses WS) stay deferred
until buyer demand.

---

## Changelog

- **2026-10-24 (match trust floors, finish HA share, speak local voice)** —
  Marked rows 191–197 Shipped (served-tier billing through Nemotron recipe
  and the HA/webhook/strip set all on main). Outward: LiteLLM 1.106.3 GA
  floor (cosign `e82a3c6`, eMudhra CA removed; 1.107 still do-not-install);
  Ollama 0.40.10 / 0.40.11-rc0 Phonon voice catalog; AAIF Skills + Open
  Responses WS; Anthropic OTel beta. Filed rows 198–202: eMudhra distrust,
  fleet-shared breakers, Phonon voices, compare-litellm 1.106.3, per-user
  RPD.

- **2026-10-23 (bill what was served, speak what went GA)** — Marked rows
  183–190 Shipped. Outward: Ollama 0.40.9; OpenAI Decisions GA; eMudhra
  distrust watch; semantic-router 1.0/1.1. Filed rows 193–197.

- **2026-10-22 + pm (finish the truths; console and day-2 packaging)** —
  Marked 171–182 Shipped. Filed 183–192. Outward: LiteLLM compromise
  post-mortem (floor 1.106.2); Anthropic enforcement_status; OpenAI
  service-tier restrictions; Ollama 0.40.8; vLLM 0.32.0.

- **2026-10-21 → 08-28** — Condensed: breaker truth, invoice-true cache
  billing, user profiles; LiteLLM compromise + Anthropic API-version
  footgun; finish-the-knobs; decisions depth; `resultType`/egress waves;
  Apache 2.0; this PRD's creation.
